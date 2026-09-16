from sqlalchemy.orm import Session

from app.models.users import User
from app.repositories.users import UserRepository
from app.schemas.user import UserRead, UserUpdate


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def update_current_user(self, user: User, payload: UserUpdate) -> UserRead:
        profile = self.users.ensure_profile(user)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is None and field == "target_roles":
                value = []
            if value is None and field == "preferences":
                value = {}
            setattr(profile, field, value)
        self.session.commit()
        self.session.refresh(user)
        return UserRead.model_validate(user)
