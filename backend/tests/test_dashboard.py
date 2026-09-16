from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.models.applications import Application
from app.models.enums import ApplicationStatus, ResumeStatus, TaskStatus, UserRole
from app.models.jobs import Job
from app.models.matching import MatchReport
from app.models.resumes import Resume, ResumeSkill, ResumeVersion, Skill
from app.models.users import User, UserProfile
from app.services.dashboard import resume_completeness


def _user(db_session: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("DashboardPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="Dashboard User"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _headers(user: User, settings: Settings) -> dict[str, str]:
    token = create_access_token(user.id, settings)
    return {"Authorization": f"Bearer {token.value}"}


def _complete_profile() -> dict[str, object]:
    return {
        "basic_info": {
            "name": {"value": "匿名候选人"},
            "email": {"value": "candidate@example.com"},
        },
        "education": [{"value": "计算机科学本科"}],
        "work_experience": [{"value": "三年后端开发经验"}],
        "project_experience": [{"value": "负责职业平台服务"}],
        "technical_skills": [{"value": "Python"}],
        "soft_skills": [{"value": "跨团队协作"}],
        "languages": [{"value": "中文"}],
        "certificates": [{"value": "云计算认证"}],
        "awards": [{"value": "优秀项目奖"}],
        "summary": {"value": "专注可靠的软件交付"},
    }


def test_resume_completeness_uses_centralized_sections() -> None:
    version = ResumeVersion(
        resume_id=1,
        version_number=1,
        structured_data=_complete_profile(),
        is_current=True,
        is_confirmed=True,
    )
    assert resume_completeness(version) == 100
    version.structured_data["summary"] = {"value": " "}
    assert resume_completeness(version) == 90
    assert resume_completeness(None) == 0


async def test_dashboard_requires_authentication(client) -> None:
    response = await client.get("/api/dashboard")
    assert response.status_code == 401


async def test_dashboard_returns_empty_real_aggregation(
    client,
    db_session: Session,
    test_settings: Settings,
) -> None:
    user = _user(db_session, "empty-dashboard@example.com")
    response = await client.get(
        "/api/dashboard",
        headers=_headers(user, test_settings),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resume_completeness"] == 0
    assert data["confirmed_version_count"] == 0
    assert data["average_match_score"] is None
    assert data["recent_resumes"] == []
    assert data["recommended_jobs"] == []


async def test_dashboard_aggregates_only_the_current_user(
    client,
    db_session: Session,
    test_settings: Settings,
) -> None:
    owner = _user(db_session, "dashboard-owner@example.com")
    other = _user(db_session, "dashboard-other@example.com")

    confirmed_resume = Resume(
        owner_id=owner.id,
        title="匿名后端工程师简历",
        status=ResumeStatus.CONFIRMED,
    )
    pending_resume = Resume(
        owner_id=owner.id,
        title="待确认简历",
        status=ResumeStatus.NEEDS_CONFIRMATION,
        parse_result={
            "basic_info": {
                "name": {"value": "候选人", "needs_confirmation": True},
            },
            "technical_skills": [
                {"value": "Python", "needs_confirmation": True},
            ],
        },
    )
    foreign_resume = Resume(
        owner_id=other.id,
        title="其他用户简历",
        status=ResumeStatus.CONFIRMED,
    )
    db_session.add_all([confirmed_resume, pending_resume, foreign_resume])
    db_session.flush()

    version = ResumeVersion(
        resume_id=confirmed_resume.id,
        version_number=1,
        structured_data=_complete_profile(),
        is_current=True,
        is_confirmed=True,
    )
    foreign_version = ResumeVersion(
        resume_id=foreign_resume.id,
        version_number=1,
        structured_data=_complete_profile(),
        is_current=True,
        is_confirmed=True,
    )
    python_skill = Skill(name="Python", category="backend")
    db_session.add_all([version, foreign_version, python_skill])
    db_session.flush()
    db_session.add(
        ResumeSkill(
            resume_version_id=version.id,
            skill_id=python_skill.id,
            raw_name="Python",
            confidence=0.98,
            evidence_text="使用 Python 构建 FastAPI 服务",
            evidence_section="work_experience",
            evidence_source_id="paragraph-3",
            source_location='{"paragraph_index": 3}',
            is_user_confirmed=True,
        )
    )

    job = Job(
        title="后端工程师",
        company="CareerPilot Demo",
        location="上海",
        description="负责 Python 服务开发",
        content_hash="a" * 64,
        status="ACTIVE",
    )
    foreign_job = Job(
        title="其他岗位",
        company="Other",
        description="other",
        content_hash="b" * 64,
        status="ACTIVE",
    )
    db_session.add_all([job, foreign_job])
    db_session.flush()
    db_session.add(
        Application(
            user_id=owner.id,
            job_id=job.id,
            status=ApplicationStatus.INTERVIEW,
        )
    )
    db_session.add_all(
        [
            MatchReport(
                user_id=owner.id,
                resume_version_id=version.id,
                job_id=job.id,
                status=TaskStatus.SUCCEEDED,
                final_score=88,
                rule_score=88,
                scoring_version="deterministic-v1.1",
                recommendation_level="RECOMMENDED",
            ),
            MatchReport(
                user_id=other.id,
                resume_version_id=foreign_version.id,
                job_id=foreign_job.id,
                status=TaskStatus.SUCCEEDED,
                final_score=12,
                rule_score=12,
                scoring_version="deterministic-v1.1",
                recommendation_level="NOT_RECOMMENDED",
            ),
        ]
    )
    db_session.commit()

    response = await client.get(
        "/api/dashboard",
        headers=_headers(owner, test_settings),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resume_completeness"] == 100
    assert data["confirmed_version_count"] == 1
    assert data["confirmed_skill_evidence_count"] == 1
    assert data["analyzed_job_count"] == 1
    assert data["average_match_score"] == 88
    assert data["recommended_job_count"] == 1
    assert data["pending_confirmation_count"] == 2
    assert {item["title"] for item in data["recent_resumes"]} == {
        "匿名后端工程师简历",
        "待确认简历",
    }
    assert data["top_skills"] == [{"name": "Python", "evidence_count": 1, "percentage": 100}]
    assert data["resume_funnel"] == {
        "uploaded": 2,
        "extracted": 2,
        "needs_confirmation": 1,
        "confirmed": 1,
    }
    assert data["weekly_application_count"] == 1
    assert data["pending_interview_count"] == 1
    assert data["application_funnel"] == {
        "saved": 0,
        "applied": 0,
        "interview": 1,
        "offer": 0,
        "rejected": 0,
    }
    assert len(data["recommended_jobs"]) == 1
    assert data["recommended_jobs"][0]["job_id"] == job.id
