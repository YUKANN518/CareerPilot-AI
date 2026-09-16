from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.users import User, UserProfile
from app.repositories.users import UserRepository


def ensure_local_demo_admin(session: Session, settings: Settings) -> bool:
    """Create the configured course-demo administrator once in local environments."""
    if not settings.should_seed_demo_admin:
        return False

    email = settings.demo_admin_email.strip().casefold()
    users = UserRepository(session)
    if users.get_by_email(email) is not None:
        return False

    user = User(
        email=email,
        password_hash=hash_password(settings.demo_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        profile=UserProfile(display_name="CareerPilot Demo Admin"),
    )
    try:
        users.add(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        if users.get_by_email(email) is None:
            raise
        return False
    return True
