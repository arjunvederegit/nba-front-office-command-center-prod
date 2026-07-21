from fastapi import Depends, Header, HTTPException

from app.config import get_settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(
            status_code=403,
            detail="Admin endpoints are disabled (no ADMIN_TOKEN configured). "
            "Use the CLI: `make sync-data`.",
        )
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


AdminDep = Depends(require_admin)
