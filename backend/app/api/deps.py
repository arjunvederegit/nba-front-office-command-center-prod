import hmac

from fastapi import Depends, Header, HTTPException

from app.config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Fails closed: with no `ADMIN_TOKEN` configured, admin routes are 403 before any
    comparison happens, so an unset token can never be matched by an empty header."""
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(
            status_code=403,
            detail="Admin endpoints are disabled (no ADMIN_TOKEN configured). "
            "Use the CLI: `make sync-data`.",
        )
    # Constant-time: `!=` on strings short-circuits at the first differing byte, which
    # leaks the length of the shared prefix to a caller who can time the response.
    if not hmac.compare_digest(x_admin_token or "", settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")


AdminDep = Depends(require_admin)
