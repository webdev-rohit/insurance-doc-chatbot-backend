import sendgrid
from sendgrid.helpers.mail import Mail
import bcrypt
import jwt
from fastapi import HTTPException
from datetime import datetime, timedelta

from apps.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")
    

def send_email(to: str, subject: str, body: str):
    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.from_email,
        to_emails=to,
        subject=subject,
        html_content=body
    )
    sg.send(message)