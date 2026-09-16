import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.files.storage import PrivateFileStorage
from app.files.validation import validate_resume_upload
from app.job_sources.normalization import normalize_job_record
from app.models.enums import JobSourceType, ResumeStatus, SourceStatus, UserRole
from app.models.jobs import Job, JobSkill, JobSource
from app.models.operations import KnowledgeDocument
from app.models.resumes import FileAsset, Resume, ResumeSkill, ResumeVersion, Skill
from app.models.users import User, UserProfile
from app.semantic.embeddings import embedding_provider_from_settings
from app.semantic.knowledge_index import KnowledgeIndexService

ADMIN_EMAIL = "admin.e2e@example.com"
ADMIN_PASSWORD = "AdminPassword123!"
MATCH_USER_EMAIL = "match.e2e@example.com"
MATCH_USER_PASSWORD = "MatchPassword123!"


def evidence_field(value: str) -> dict[str, object]:
    return {
        "value": value,
        "confidence": 1,
        "evidence_text": value,
        "source_location": {
            "source_type": "page",
            "page_number": 1,
            "block_index": 0,
            "paragraph_index": None,
            "table_index": None,
            "row_index": None,
            "label": "page:1:block:0",
        },
        "needs_confirmation": False,
    }


def structured_resume() -> dict[str, object]:
    return {
        "basic_info": {
            "full_name": evidence_field("Anonymous Match Candidate"),
            "email": evidence_field("match@example.test"),
            "phone": evidence_field("00000000000"),
            "location": evidence_field("Shanghai"),
        },
        "education": [
            {
                "institution": evidence_field("Fixture University"),
                "degree": evidence_field("Bachelor"),
                "field_of_study": evidence_field("Computer Science"),
                "start_date": evidence_field("2016-09"),
                "end_date": evidence_field("2020-06"),
                "description": evidence_field("Software engineering curriculum."),
            }
        ],
        "work_experience": [
            {
                "company": evidence_field("Fixture Labs"),
                "title": evidence_field("Backend Engineer"),
                "start_date": evidence_field("2020-01"),
                "end_date": evidence_field("2025-12"),
                "description": evidence_field("Built production Python and SQL services."),
            }
        ],
        "project_experience": [],
        "technical_skills": [],
        "soft_skills": [],
        "languages": [evidence_field("English")],
        "certificates": [],
        "awards": [],
        "summary": evidence_field("Anonymous deterministic matching fixture."),
    }


def attach_job_skill(session, job: Job, skill: Skill) -> None:
    if any(item.skill_id == skill.id for item in job.skills):
        return
    job.skills.append(
        JobSkill(
            skill=skill,
            is_required=True,
            weight=2,
            evidence_text="Python is required.",
        )
    )


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        admin = session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            admin = User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                profile=UserProfile(display_name="E2E Administrator"),
            )
            session.add(admin)
            session.flush()

        match_user = session.scalar(select(User).where(User.email == MATCH_USER_EMAIL))
        if match_user is None:
            match_user = User(
                email=MATCH_USER_EMAIL,
                password_hash=hash_password(MATCH_USER_PASSWORD),
                role=UserRole.USER,
                profile=UserProfile(
                    display_name="E2E Match User",
                    location="Shanghai",
                    preferences={
                        "work_eligibility": False,
                        "preferred_locations": ["Shanghai"],
                        "employment_types": ["FULL_TIME"],
                    },
                ),
            )
            session.add(match_user)
            session.flush()

        other_user = session.scalar(select(User).where(User.email == "other.e2e@example.com"))
        if other_user is None:
            other_user = User(
                email="other.e2e@example.com",
                password_hash=hash_password(MATCH_USER_PASSWORD),
                role=UserRole.USER,
                profile=UserProfile(display_name="Other E2E User"),
            )
            session.add(other_user)
            session.flush()

        python_skill = session.scalar(select(Skill).where(Skill.name == "Python"))
        if python_skill is None:
            python_skill = Skill(name="Python", category="TECHNICAL")
            session.add(python_skill)
            session.flush()

        docker_skill = session.scalar(select(Skill).where(Skill.name == "Docker"))
        if docker_skill is None:
            docker_skill = Skill(name="Docker", category="TECHNICAL")
            session.add(docker_skill)
            session.flush()

        resume = session.scalar(
            select(Resume).where(
                Resume.owner_id == match_user.id,
                Resume.title == "E2E Confirmed Resume",
            )
        )
        if resume is None:
            asset = FileAsset(
                owner_id=match_user.id,
                storage_key="e2e/match-resume.pdf",
                original_name="anonymous-match-resume.pdf",
                mime_type="application/pdf",
                size_bytes=64,
                sha256="f" * 64,
                file_format="pdf",
            )
            resume = Resume(
                owner_id=match_user.id,
                file_asset=asset,
                title="E2E Confirmed Resume",
                status=ResumeStatus.CONFIRMED,
                confirmed_at=datetime.now(UTC),
            )
            version = ResumeVersion(
                resume=resume,
                version_number=1,
                raw_text="Anonymous generated fixture.",
                structured_data=structured_resume(),
                is_current=True,
                is_confirmed=True,
            )
            version.skills.append(
                ResumeSkill(
                    skill=python_skill,
                    raw_name="Python",
                    confidence=0.96,
                    evidence_text="Built production Python and SQL services.",
                    evidence_section="work_experience",
                    evidence_source_id="page-1",
                    source_location=json.dumps(
                        {
                            "source_type": "page",
                            "page_number": 1,
                            "block_index": 0,
                            "label": "page:1:block:0",
                        }
                    ),
                    is_user_confirmed=True,
                )
            )
            session.add(resume)

        source = session.scalar(
            select(JobSource).where(JobSource.name == "CareerPilot E2E Seed Careers")
        )
        if source is None:
            source = JobSource(
                created_by_id=admin.id,
                name="CareerPilot E2E Seed Careers",
                source_type=JobSourceType.MANUAL,
                status=SourceStatus.ENABLED,
                base_url="https://jobs.example.com",
                region="CN",
                language="zh-CN",
                sync_frequency_minutes=60,
                is_enabled=True,
                last_tested_at=datetime.now(UTC),
                last_test_succeeded=True,
                last_sync_at=datetime.now(UTC),
            )
            session.add(source)
            session.flush()

        existing_job = session.scalar(
            select(Job).where(
                Job.source_id == source.id,
                Job.external_job_id == "seed-job-1",
            )
        )
        if existing_job is None:
            candidate = normalize_job_record(
                source.id,
                {
                    "external_job_id": "seed-job-1",
                    "title": "Seeded Backend Engineer",
                    "company": "CareerPilot E2E",
                    "location": "Shanghai",
                    "salary_min": "24000",
                    "salary_max": "36000",
                    "currency": "CNY",
                    "employment_type": "FULL_TIME",
                    "experience_level": "MID",
                    "education_requirement": "BACHELOR",
                    "description": "Build reliable Python services for CareerPilot.",
                    "requirements": "Python and SQL",
                    "source_url": "https://jobs.example.com/seed-job-1",
                    "published_at": datetime.now(UTC),
                },
            )
            existing_job = Job(
                **candidate.model_dump(mode="python"),
                owner_id=None,
                import_method=None,
            )
            session.add(existing_job)
            session.flush()
        attach_job_skill(session, existing_job, python_skill)

        fixture_jobs = (
            {
                "external_job_id": "blocking-job",
                "title": "Eligibility Blocked Engineer",
                "company": "CareerPilot E2E",
                "location": "Shanghai",
                "description": "Build Python services.",
                "requirements": (
                    "Python is required. Candidate must have work authorization in China."
                ),
                "employment_type": "FULL_TIME",
                "experience_level": "MID",
                "education_requirement": "BACHELOR",
                "language_requirements": ["English"],
                "source_url": "https://jobs.example.com/blocking-job",
                "published_at": datetime.now(UTC),
            },
            {
                "external_job_id": "incomplete-job",
                "title": "Incomplete Fixture Engineer",
                "company": "CareerPilot E2E",
                "description": "Build Python services.",
                "source_url": "https://jobs.example.com/incomplete-job",
                "published_at": datetime.now(UTC),
            },
            {
                "external_job_id": "skill-gap-job",
                "title": "Skill Gap Engineer",
                "company": "CareerPilot E2E",
                "location": "Shanghai",
                "salary_min": "24000",
                "salary_max": "36000",
                "currency": "CNY",
                "employment_type": "FULL_TIME",
                "experience_level": "SENIOR",
                "education_requirement": "BACHELOR",
                "description": "Build and ship Python services in containers.",
                "requirements": "Python and Docker are required.",
                "language_requirements": ["English"],
                "source_url": "https://jobs.example.com/skill-gap-job",
                "published_at": datetime.now(UTC),
            },
        )
        for fixture in fixture_jobs:
            fixture_job = session.scalar(
                select(Job).where(
                    Job.source_id == source.id,
                    Job.external_job_id == fixture["external_job_id"],
                )
            )
            if fixture_job is None:
                normalized = normalize_job_record(source.id, fixture)
                fixture_job = Job(
                    **normalized.model_dump(mode="python"),
                    owner_id=None,
                    import_method=None,
                )
                session.add(fixture_job)
                session.flush()
            attach_job_skill(session, fixture_job, python_skill)
            if fixture["external_job_id"] == "skill-gap-job" and not any(
                item.skill_id == docker_skill.id for item in fixture_job.skills
            ):
                fixture_job.skills.append(
                    JobSkill(
                        skill=docker_skill,
                        is_required=True,
                        weight=2,
                        evidence_text="Docker is required.",
                    )
                )

        # Stage 2: JobsDB and OfferToday public summary seed jobs.
        jobsdb_source = session.scalar(
            select(JobSource).where(JobSource.name == "JobsDB · 香港公开岗位快照")
        )
        if jobsdb_source is None:
            jobsdb_source = JobSource(
                created_by_id=admin.id,
                name="JobsDB · 香港公开岗位快照",
                source_type=JobSourceType.MANUAL,
                status=SourceStatus.ENABLED,
                base_url="https://hk.jobsdb.com/",
                region="Hong Kong",
                language="en",
                is_enabled=True,
                last_sync_at=datetime.now(UTC),
            )
            session.add(jobsdb_source)
            session.flush()

        offertoday_source = session.scalar(
            select(JobSource).where(JobSource.name == "OfferToday · 香港公开岗位快照")
        )
        if offertoday_source is None:
            offertoday_source = JobSource(
                created_by_id=admin.id,
                name="OfferToday · 香港公开岗位快照",
                source_type=JobSourceType.MANUAL,
                status=SourceStatus.ENABLED,
                base_url="https://m.offertoday.com/en/",
                region="Hong Kong",
                language="en",
                is_enabled=True,
                last_sync_at=datetime.now(UTC),
            )
            session.add(offertoday_source)
            session.flush()

        stage2_jobs = (
            {
                "source_id": jobsdb_source.id,
                "external_job_id": "jobsdb-e2e-1",
                "title": "JobsDB Python Backend Developer",
                "company": "JobsDB E2E Fintech",
                "location": "Hong Kong",
                "description": "Build reliable Python APIs for a Hong Kong fintech platform.",
                "source_url": "https://hk.jobsdb.com/job/e2e-python-backend",
                "published_at": datetime.now(UTC),
            },
            {
                "source_id": jobsdb_source.id,
                "external_job_id": "jobsdb-e2e-2",
                "title": "JobsDB QA Engineer",
                "company": "JobsDB E2E Test Corp",
                "location": "Kowloon",
                "description": "Ensure quality of web and mobile applications.",
                "source_url": "https://hk.jobsdb.com/job/e2e-qa-engineer",
                "published_at": datetime.now(UTC),
            },
            {
                "source_id": offertoday_source.id,
                "external_job_id": "offertoday-e2e-1",
                "title": "OfferToday Data Analyst",
                "company": "OfferToday E2E Data",
                "location": "Hong Kong",
                "description": "Analyse business data and build dashboards.",
                "source_url": "https://m.offertoday.com/en/job/e2e-data-analyst",
                "published_at": datetime.now(UTC),
            },
            {
                "source_id": offertoday_source.id,
                "external_job_id": "offertoday-e2e-2",
                "title": "OfferToday Product Designer",
                "company": "OfferToday E2E Design",
                "location": "Central",
                "description": "Design user-centric product interfaces.",
                "source_url": "https://m.offertoday.com/en/job/e2e-product-designer",
                "published_at": datetime.now(UTC),
            },
        )
        for stage2_job in stage2_jobs:
            existing = session.scalar(
                select(Job).where(
                    Job.source_id == stage2_job["source_id"],
                    Job.external_job_id == stage2_job["external_job_id"],
                )
            )
            if existing is None:
                normalized = normalize_job_record(stage2_job["source_id"], stage2_job)
                session.add(
                    Job(
                        **normalized.model_dump(mode="python"),
                        owner_id=None,
                        import_method=None,
                    )
                )
        session.flush()

        private_job = session.scalar(
            select(Job).where(
                Job.owner_id == other_user.id,
                Job.external_job_id == "private-other-job",
            )
        )
        if private_job is None:
            private = normalize_job_record(
                None,
                {
                    "external_job_id": "private-other-job",
                    "title": "Other User Private Job",
                    "company": "Private Fixture",
                    "description": "A private job fixture.",
                },
            )
            session.add(
                Job(
                    **private.model_dump(mode="python"),
                    owner_id=other_user.id,
                    import_method="USER_MANUAL",
                )
            )
        session.flush()

        # Stage 4A: seed a knowledge document for Career Assistant QA.
        knowledge_doc = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.uploaded_by_id == admin.id,
                KnowledgeDocument.title == "E2E Career Knowledge Guide",
            )
        )
        if knowledge_doc is None:
            fixture_pdf = (
                Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_resume.pdf"
            )
            content = fixture_pdf.read_bytes()
            settings = get_settings()
            storage = PrivateFileStorage(settings.upload_directory)
            validated = validate_resume_upload(
                "career-guide.pdf",
                "application/pdf",
                content,
                settings.resume_max_upload_bytes,
            )
            storage_key = storage.save(
                admin.id,
                validated.file_format,
                validated.content,
            )
            asset = FileAsset(
                owner_id=admin.id,
                storage_key=storage_key,
                original_name=validated.original_name,
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
                sha256=validated.sha256,
                file_format=validated.file_format,
            )
            session.add(asset)
            session.flush()
            knowledge_doc = KnowledgeDocument(
                uploaded_by_id=admin.id,
                file_asset_id=asset.id,
                title="E2E Career Knowledge Guide",
                category="guide",
                status="PENDING",
                chunk_count=0,
                metadata_json={},
            )
            session.add(knowledge_doc)
            session.flush()
            index_service = KnowledgeIndexService(
                settings,
                embedding_provider_from_settings(settings),
                session,
            )
            index_service.index_document(knowledge_doc)

        session.commit()


if __name__ == "__main__":
    seed()
