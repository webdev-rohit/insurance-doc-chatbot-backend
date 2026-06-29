from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .repository import AuthRepository
from apps.core.config import settings
from apps.core.global_utils import logOperation
from .utils import hash_password, verify_password, create_token, decode_token, send_email


class AuthService:
    def __init__(self, db: Session):
        self.repo = AuthRepository(db)
        self.db = db

    @logOperation
    def register(self, email: str, first_name: str, last_name: str, password: str):
        existing = self.repo.get_user_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        password_hash = hash_password(password)
        self.repo.create_user(email, first_name, last_name, password_hash)
        self.db.commit()  

        token = create_token(
            {"sub": email, "type": "verify"},
            timedelta(hours=settings.verify_token_expire_hours)
        )
        send_email(
            to=email,
            subject="Verify your email",
            body=f"<p>Use the token below to verify your account:</p><pre>{token}</pre>"
        )

        return {"message": "Registered successfully. Check email to verify.", "verify_token": token}

    @logOperation
    def verify_email(self, token: str):
        payload = decode_token(token)
        if payload.get("type") != "verify":
            raise HTTPException(status_code=400, detail="Invalid token type")

        user = self.repo.get_user_by_email(payload["sub"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.is_verified:
            raise HTTPException(status_code=400, detail="Already verified")

        self.repo.verify_user(str(user.id))
        self.db.commit()
        return {"message": "Email verified successfully"}

    @logOperation
    def login(self, email: str, password: str):
        user = self.repo.get_user_by_email(email)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_verified:
            raise HTTPException(
                status_code=403,
                detail="Your email is not verified. Please check your inbox and click the verification link before logging in."
            )
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_token(
            {"sub": str(user.id), "type": "access"},
            timedelta(minutes=settings.access_token_expire_minutes)
        )
        return {"access_token": token, "token_type": "bearer"}

    @logOperation
    def forgot_password(self, email: str):
        user = self.repo.get_user_by_email(email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        token = create_token(
            {"sub": str(user.id), "type": "reset"},
            timedelta(minutes=settings.reset_token_expire_minutes)
        )
        send_email(
            to=email,
            subject="Reset your password",
            body=f"<p>Use the token below to reset your password:</p><pre>{token}</pre>"
        )

        return {"message": "Password reset link sent.", "reset_token": token}

    @logOperation
    def reset_password(self, token: str, new_password: str):
        payload = decode_token(token)
        if payload.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid token type")

        user = self.repo.get_user_by_id(payload["sub"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if verify_password(new_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail="New password cannot be the same as the old password. Please try a different one."
            )

        self.repo.update_password(str(user.id), hash_password(new_password))
        self.db.commit()
        return {"message": "Password reset successfully"}