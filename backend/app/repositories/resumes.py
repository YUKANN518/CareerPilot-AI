from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.resumes import (
    FileAsset,
    Resume,
    ResumeSkill,
    ResumeVersion,
    Skill,
    SkillAlias,
)


class ResumeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_owner(self, owner_id: int) -> list[Resume]:
        statement = (
            select(Resume)
            .where(Resume.owner_id == owner_id)
            .options(selectinload(Resume.file_asset), selectinload(Resume.versions))
            .order_by(Resume.updated_at.desc())
        )
        return list(self.session.scalars(statement).all())

    def get_for_owner(self, resume_id: int, owner_id: int) -> Resume | None:
        statement = (
            select(Resume)
            .where(Resume.id == resume_id, Resume.owner_id == owner_id)
            .options(selectinload(Resume.file_asset), selectinload(Resume.versions))
        )
        return self.session.scalar(statement)

    def find_asset_by_hash(self, owner_id: int, content_hash: str) -> FileAsset | None:
        return self.session.scalar(
            select(FileAsset).where(
                FileAsset.owner_id == owner_id,
                FileAsset.sha256 == content_hash,
            )
        )

    def find_resume_by_asset(self, owner_id: int, asset_id: int) -> Resume | None:
        statement = (
            select(Resume)
            .where(Resume.owner_id == owner_id, Resume.file_asset_id == asset_id)
            .options(selectinload(Resume.file_asset), selectinload(Resume.versions))
            .order_by(Resume.created_at.desc())
        )
        return self.session.scalars(statement).first()

    def count_asset_references(self, asset_id: int) -> int:
        statement = select(func.count(Resume.id)).where(Resume.file_asset_id == asset_id)
        return int(self.session.scalar(statement) or 0)

    def next_version_number(self, resume_id: int) -> int:
        statement = select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.resume_id == resume_id
        )
        return int(self.session.scalar(statement) or 0) + 1

    def list_versions(self, resume_id: int, owner_id: int) -> list[ResumeVersion]:
        statement = (
            select(ResumeVersion)
            .join(Resume)
            .where(ResumeVersion.resume_id == resume_id, Resume.owner_id == owner_id)
            .order_by(ResumeVersion.version_number.desc())
        )
        return list(self.session.scalars(statement).all())

    def get_version_for_owner(self, version_id: int, owner_id: int) -> ResumeVersion | None:
        statement = (
            select(ResumeVersion)
            .join(Resume)
            .where(ResumeVersion.id == version_id, Resume.owner_id == owner_id)
            .options(selectinload(ResumeVersion.skills).selectinload(ResumeSkill.skill))
        )
        return self.session.scalar(statement)

    def find_skill(self, raw_name: str) -> Skill | None:
        normalized = raw_name.strip().casefold()
        direct = self.session.scalar(select(Skill).where(func.lower(Skill.name) == normalized))
        if direct is not None:
            return direct
        return self.session.scalar(
            select(Skill).join(SkillAlias).where(func.lower(SkillAlias.alias) == normalized)
        )
