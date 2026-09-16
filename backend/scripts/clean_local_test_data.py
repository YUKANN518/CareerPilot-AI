from contextlib import suppress
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.resumes import FileAsset
from app.models.users import User

TEST_EMAIL_PREFIXES = ("e2e-", "jobs-e2e-", "resume-e2e-")


def main() -> None:
    settings = get_settings()
    configured_upload_root = Path(settings.upload_directory)
    backend_root = Path(__file__).resolve().parents[1]
    upload_root = (
        configured_upload_root
        if configured_upload_root.is_absolute()
        else backend_root / configured_upload_root
    ).resolve()
    storage_paths: list[Path] = []

    with SessionLocal() as session:
        users = [
            user
            for user in session.scalars(select(User))
            if user.email.casefold().startswith(TEST_EMAIL_PREFIXES)
        ]
        user_ids = [user.id for user in users]
        if user_ids:
            assets = session.scalars(select(FileAsset).where(FileAsset.owner_id.in_(user_ids)))
            for asset in assets:
                path = (upload_root / asset.storage_key).resolve()
                if path.is_relative_to(upload_root):
                    storage_paths.append(path)
            for user in users:
                session.delete(user)
        session.commit()

    for path in storage_paths:
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent != upload_root:
            with suppress(OSError):
                parent.rmdir()

    print(
        f"Removed {len(user_ids)} local E2E users and {len(storage_paths)} associated test files."
    )


if __name__ == "__main__":
    main()
