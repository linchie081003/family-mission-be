import hashlib
import secrets
from datetime import datetime, timedelta, timezone


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
