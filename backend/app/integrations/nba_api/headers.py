"""Browser-like request headers for stats.nba.com.

nba_api ships a workable default header set; we keep it and only override the
User-Agent when the operator supplies one (some networks require rotation)."""

from app.config import get_settings

DEFAULT_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
}


def build_headers() -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    settings = get_settings()
    if settings.nba_api_user_agent:
        headers["User-Agent"] = settings.nba_api_user_agent
    return headers


def build_proxy() -> str | None:
    settings = get_settings()
    return settings.nba_api_http_proxy or None
