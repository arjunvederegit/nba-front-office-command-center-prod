"""Request headers for stats.nba.com.

nba_api ships a header set that stats.nba.com accepts; empirically, deviating from it
(different Referer/Origin combinations) causes the edge to hang the request until
timeout. We therefore defer to the package defaults and only override the User-Agent
when the operator explicitly configures one."""

from app.config import get_settings


def build_headers() -> dict[str, str] | None:
    """None → nba_api uses its own proven default header set."""
    settings = get_settings()
    if settings.nba_api_user_agent:
        return {"User-Agent": settings.nba_api_user_agent}
    return None


def build_proxy() -> str | None:
    settings = get_settings()
    return settings.nba_api_http_proxy or None
