"""Optional bearer-token auth dependency.

If `API_AUTH_TOKEN` is unset, auth is disabled and every request passes — this
keeps local development frictionless. When set, every route that depends on
`require_auth` must present `Authorization: Bearer <token>`.

`/api/health` is intentionally unauthenticated so uptime checks work.
"""
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings


def _extract_token(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    # Accept the raw token too — common for curl testing.
    return header.strip() or None


def require_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().api_auth_token
    if not expected:
        return  # auth disabled
    provided = _extract_token(authorization)
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


AuthDep = Depends(require_auth)
