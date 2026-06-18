from sqlalchemy.orm import Session
from sqlalchemy import insert, select, update

from .models import User


class AuthRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, email: str, first_name: str, last_name: str, password_hash: str):
        stmt = insert(User).values(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            is_verified=False
        ).returning(User)
        return self.db.execute(stmt)

    def get_user_by_email(self, email: str):
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: str):
        stmt = select(User).where(User.id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def verify_user(self, user_id: str):
        stmt = update(User).where(User.id == user_id).values(is_verified=True)
        return self.db.execute(stmt)

    def update_password(self, user_id: str, password_hash: str):
        stmt = update(User).where(User.id == user_id).values(password_hash=password_hash)
        return self.db.execute(stmt)