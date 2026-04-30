"""Auth endpoints: login, logout, me."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core import rate_limit, sessions
from app.core.auth import COOKIE_NAME, AuthDep, verify_password
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str


def _client_ip(request: Request) -> str:
    # Direct connection only for v1; document proxy caveats in the spec.
    if request.client is None:
        return "unknown"
    return request.client.host


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=sessions.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    settings = get_settings()
    if not settings.auth_username or not settings.auth_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth not configured on this server",
        )

    ip = _client_ip(request)
    try:
        rate_limit.check_login_ip(ip)
    except rate_limit.RateLimited as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts",
            headers={"Retry-After": str(e.retry_after_seconds)},
        ) from None

    ok = (
        body.username == settings.auth_username
        and verify_password(body.password, settings.auth_password_hash)
    )
    if not ok:
        rate_limit.register_login_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    sid = sessions.create_session(body.username)
    _set_session_cookie(response, sid)
    return LoginResponse(username=body.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> Response:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        sessions.destroy_session(cookie)
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=LoginResponse)
def me(username: Annotated[str, AuthDep]) -> LoginResponse:
    return LoginResponse(username=username)
