from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext # For actual password hashing

from app.core.config import settings
from app.core.logger import app_logger

# For this example, we'll skip password hashing complexity,
# but in a real app, you'd use something like:
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_password(plain_password, hashed_password):
    # In a real app: return pwd_context.verify(plain_password, hashed_password)
    return plain_password == hashed_password # Simplified for demo

def get_password_hash(password):
    # In a real app: return pwd_context.hash(password)
    return password # Simplified for demo