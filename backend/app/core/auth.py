"""Password hashing + cookie-based session dependency."""
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, status

from app.core.sessions import get_session_username

COOKIE_NAME = "etherscope_session"

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def require_auth(
    etherscope_session: Annotated[str | None, Cookie()] = None,
) -> str:
    username = get_session_username(etherscope_session or "")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return username


AuthDep = Depends(require_auth)
