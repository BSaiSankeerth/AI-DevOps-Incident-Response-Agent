"""Password hashing (bcrypt) and JWT login tokens."""
import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import db
from app.config import JWT_EXPIRE_MINUTES, JWT_SECRET

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    if not JWT_SECRET:
        raise HTTPException(500, "JWT_SECRET is not set in Backend/.env")
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """FastAPI dependency: returns {'id','username'} or raises 401."""
    if not JWT_SECRET:
        raise HTTPException(500, "JWT_SECRET is not set in Backend/.env")
    if credentials is None:
        raise HTTPException(401, "Not logged in")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid login token")

    user = db.get_user(payload.get("sub", ""))
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return user