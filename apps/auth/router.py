from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .schemas import (
    RegisterRequest, RegisterResponse,
    VerifyEmailRequest, VerifyEmailResponse,
    LoginRequest, LoginResponse,
    ForgotPasswordRequest, ForgotPasswordResponse,
    ResetPasswordRequest, ResetPasswordResponse,
)
from .services import AuthService
from apps.core.database import get_db


router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    return AuthService(db).register(request.email, request.password)

@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(request: VerifyEmailRequest, db: Session = Depends(get_db)):
    return AuthService(db).verify_email(request.token)

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    return AuthService(db).login(request.email, request.password)

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    return AuthService(db).forgot_password(request.email)

@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    return AuthService(db).reset_password(request.token, request.new_password)