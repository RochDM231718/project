from datetime import datetime, timedelta, UTC
from jose import jwt, JWTError
from typing import Optional, Dict
from dotenv import load_dotenv
import os

load_dotenv()

ALGORITHM = "HS256"

SECRET_KEY = os.getenv("API_SECRET_KEY")
REFRESH_SECRET_KEY = os.getenv("API_REFRESH_SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("CRITICAL SECURITY ERROR: API_SECRET_KEY is not set in environment variables!")
if not REFRESH_SECRET_KEY:
    raise ValueError("CRITICAL SECURITY ERROR: API_REFRESH_SECRET_KEY is not set in environment variables!")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("API_ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("API_REFRESH_TOKEN_EXPIRE_DAYS", 7))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, refresh: bool = False) -> Optional[Dict]:
    try:
        secret = REFRESH_SECRET_KEY if refresh else SECRET_KEY
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None