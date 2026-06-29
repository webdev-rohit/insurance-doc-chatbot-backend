import re
from pydantic import BaseModel, EmailStr, Field, field_validator


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one number")
    return v


# ── Request schemas ──────────────────────────────────────────────────────────

def _validate_name(v: str, field: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{field} cannot be empty")
    if not re.fullmatch(r"[A-Za-z\s'\-]+", v):
        raise ValueError(f"{field} must contain only letters, spaces, hyphens, or apostrophes")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., example="john.doe@example.com")
    first_name: str = Field(..., min_length=1, max_length=100, example="John")
    last_name: str = Field(..., min_length=1, max_length=100, example="Doe")
    password: str = Field(..., example="secure_password1")

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v):
        return _validate_name(v, "First name")

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, v):
        return _validate_name(v, "Last name")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        return _validate_password(v)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., example="verification_token")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="john.doe@example.com")
    password: str = Field(..., example="secure_password1")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., example="john.doe@example.com")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., example="reset_token")
    new_password: str = Field(..., example="new_secure_password1")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        return _validate_password(v)


# ── Response schemas ──────────────────────────────────────────────────────────

class RegisterResponse(BaseModel):
    message: str
    verify_token: str


class VerifyEmailResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str


class ResetPasswordResponse(BaseModel):
    message: str
