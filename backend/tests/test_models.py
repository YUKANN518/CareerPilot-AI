from datetime import UTC, datetime

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.users import RefreshToken, User, UserProfile

EXPECTED_TABLES = {
    "agent_runs",
    "agent_steps",
    "application_status_history",
    "applications",
    "audit_logs",
    "file_assets",
    "generated_materials",
    "interview_messages",
    "interview_questions",
    "interview_sessions",
    "job_favorites",
    "job_skills",
    "job_sources",
    "jobs",
    "knowledge_documents",
    "match_details",
    "match_evidence",
    "match_reports",
    "model_usage_logs",
    "prompt_templates",
    "prompt_versions",
    "refresh_tokens",
    "resume_sections",
    "resume_skills",
    "resume_versions",
    "resumes",
    "skill_aliases",
    "skills",
    "system_settings",
    "user_profiles",
    "users",
}


def test_core_schema_contains_all_required_tables(db_session: Session) -> None:
    assert set(inspect(db_session.get_bind()).get_table_names()) == EXPECTED_TABLES
    assert db_session.scalar(text("PRAGMA foreign_keys")) == 1


def test_user_owned_identity_data_cascades_on_delete(db_session: Session) -> None:
    user = User(
        email="cascade@example.com",
        password_hash=hash_password("StrongPassword123!"),
        profile=UserProfile(display_name="Cascade"),
    )
    user.refresh_tokens.append(
        RefreshToken(
            jti="00000000-0000-0000-0000-000000000001",
            token_hash="a" * 64,
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        )
    )
    db_session.add(user)
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.scalar(select(UserProfile)) is None
    assert db_session.scalar(select(RefreshToken)) is None
