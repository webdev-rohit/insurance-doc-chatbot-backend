from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from apps.auth.utils import decode_token

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload["sub"]  # user UUID string

# Custom decorator for logging function operations in the application
def logOperation(func):
    def wrapper(*args, **kwargs):
        print(f"\n---Executing {func.__name__} function -----")
        result = func(*args, **kwargs)
        return result
    return wrapper