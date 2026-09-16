from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.users import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_jti(self, jti: str) -> RefreshToken | None:
        return self.session.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
