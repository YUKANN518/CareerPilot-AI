from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.users import User, UserProfile


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email).options(selectinload(User.profile))
        return self.session.scalar(statement)

    def get_by_id(self, user_id: int) -> User | None:
        statement = select(User).where(User.id == user_id).options(selectinload(User.profile))
        return self.session.scalar(statement)

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def ensure_profile(self, user: User) -> UserProfile:
        if user.profile is None:
            user.profile = UserProfile()
            self.session.flush()
        return user.profile
