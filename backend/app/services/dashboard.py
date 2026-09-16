from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from app.models.enums import ApplicationStatus, ResumeStatus
from app.models.resumes import Resume, ResumeVersion
from app.models.users import User
from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import (
    DashboardApplicationFunnelRead,
    DashboardRead,
    DashboardRecommendedJobRead,
    DashboardResumeFunnelRead,
    DashboardResumeRead,
    DashboardSkillRead,
)

COMPLETENESS_WEIGHTS = {
    "basic_info": 15,
    "education": 10,
    "work_experience": 15,
    "project_experience": 15,
    "technical_skills": 15,
    "soft_skills": 5,
    "languages": 5,
    "certificates": 5,
    "awards": 5,
    "summary": 10,
}

RESUME_PROGRESS = {
    ResumeStatus.UPLOADED: 20,
    ResumeStatus.EXTRACTING: 35,
    ResumeStatus.EXTRACTED: 55,
    ResumeStatus.PARSING: 70,
    ResumeStatus.NEEDS_CONFIRMATION: 85,
    ResumeStatus.CONFIRMED: 100,
    ResumeStatus.FAILED: 20,
    ResumeStatus.ARCHIVED: 100,
}


def _field_value(value: object) -> object:
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _is_present(value: object) -> bool:
    candidate = _field_value(value)
    if candidate is None:
        return False
    if isinstance(candidate, str):
        return bool(candidate.strip())
    if isinstance(candidate, Mapping):
        return any(_is_present(item) for item in candidate.values())
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        return any(_is_present(item) for item in candidate)
    return True


def resume_completeness(version: ResumeVersion | None) -> int:
    if version is None:
        return 0
    data = version.structured_data
    score = 0.0
    for section, weight in COMPLETENESS_WEIGHTS.items():
        value = data.get(section)
        if section == "basic_info" and isinstance(value, Mapping):
            fields = list(value.values())
            filled = sum(_is_present(item) for item in fields)
            score += weight * (filled / len(fields) if fields else 0)
        elif _is_present(value):
            score += weight
    return max(0, min(100, round(score)))


def _confirmation_count(value: object) -> int:
    if isinstance(value, Mapping):
        own = int(value.get("needs_confirmation") is True)
        return own + sum(_confirmation_count(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_confirmation_count(item) for item in value)
    return 0


def _resume_read(resume: Resume) -> DashboardResumeRead:
    file_type = resume.file_asset.file_format.upper() if resume.file_asset is not None else None
    return DashboardResumeRead(
        id=resume.id,
        title=resume.title,
        file_type=file_type,
        status=resume.status,
        progress=RESUME_PROGRESS[resume.status],
        updated_at=resume.updated_at,
    )


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.repository = DashboardRepository(session)

    def get(self, user: User) -> DashboardRead:
        status_counts = self.repository.resume_status_counts(user.id)
        analyzed_jobs, average_score, recommended_jobs = self.repository.match_summary(user.id)
        skill_rows = self.repository.top_confirmed_skills(user.id)
        maximum_evidence = max((count for _, count in skill_rows), default=0)
        pending_count = sum(
            _confirmation_count(result) for result in self.repository.pending_parse_results(user.id)
        )
        application_counts, weekly_application_count, pending_interview_count = (
            self.repository.application_summary(user.id)
        )

        unique_jobs: set[int] = set()
        recommendations: list[DashboardRecommendedJobRead] = []
        for report, job in self.repository.recent_recommended_reports(user.id):
            if job.id in unique_jobs or report.final_score is None:
                continue
            unique_jobs.add(job.id)
            recommendations.append(
                DashboardRecommendedJobRead(
                    report_id=report.id,
                    job_id=job.id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    final_score=round(report.final_score, 1),
                    recommendation=report.recommendation_level or "UNKNOWN",
                    scoring_version=report.scoring_version,
                    created_at=report.created_at,
                )
            )
            if len(recommendations) == 3:
                break

        extracted_statuses = {
            ResumeStatus.EXTRACTED,
            ResumeStatus.PARSING,
            ResumeStatus.NEEDS_CONFIRMATION,
            ResumeStatus.CONFIRMED,
            ResumeStatus.ARCHIVED,
        }
        return DashboardRead(
            resume_completeness=resume_completeness(
                self.repository.current_confirmed_version(user.id)
            ),
            confirmed_version_count=self.repository.confirmed_version_count(user.id),
            confirmed_skill_evidence_count=self.repository.confirmed_skill_evidence_count(user.id),
            analyzed_job_count=analyzed_jobs,
            average_match_score=(round(average_score, 1) if average_score is not None else None),
            recommended_job_count=recommended_jobs,
            pending_confirmation_count=pending_count,
            recent_resumes=[
                _resume_read(resume) for resume in self.repository.recent_resumes(user.id)
            ],
            top_skills=[
                DashboardSkillRead(
                    name=name,
                    evidence_count=count,
                    percentage=(round(count / maximum_evidence * 100) if maximum_evidence else 0),
                )
                for name, count in skill_rows
            ],
            resume_funnel=DashboardResumeFunnelRead(
                uploaded=sum(status_counts.values()),
                extracted=sum(
                    count for status, count in status_counts.items() if status in extracted_statuses
                ),
                needs_confirmation=status_counts.get(ResumeStatus.NEEDS_CONFIRMATION, 0),
                confirmed=(
                    status_counts.get(ResumeStatus.CONFIRMED, 0)
                    + status_counts.get(ResumeStatus.ARCHIVED, 0)
                ),
            ),
            application_funnel=DashboardApplicationFunnelRead(
                saved=application_counts.get(ApplicationStatus.SAVED, 0),
                applied=application_counts.get(ApplicationStatus.APPLIED, 0),
                interview=application_counts.get(ApplicationStatus.INTERVIEW, 0),
                offer=application_counts.get(ApplicationStatus.OFFER, 0),
                rejected=application_counts.get(ApplicationStatus.REJECTED, 0),
            ),
            weekly_application_count=weekly_application_count,
            pending_interview_count=pending_interview_count,
            recommended_jobs=recommendations,
        )
