from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
CAP_RULES_DIR = Path(__file__).resolve().parent / "cap_rules"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./tradelab.db"
    redis_url: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    admin_token: str = ""

    nba_api_timeout_seconds: float = 45.0
    nba_api_max_retries: int = 4
    nba_api_min_request_interval_seconds: float = 0.75
    nba_api_max_concurrency: int = 2
    nba_api_cache_ttl_seconds: int = 3600
    nba_api_stale_after_seconds: int = 86400
    nba_api_user_agent: str = ""
    nba_api_http_proxy: str = ""

    current_season: str = "2025-26"
    history_seasons: str = "2023-24,2024-25,2025-26"
    # League year whose cap parameters govern trade legality (trades executed in July
    # 2026 fall under the 2026-27 cap even though the latest completed stats season
    # is 2025-26).
    cap_league_year: str = "2026-27"

    contract_data_provider: str = ""
    contract_data_api_key: str = ""
    contract_data_file: str = ""

    injury_data_provider: str = ""
    live_data_enabled: bool = False

    anthropic_api_key: str = ""

    # --- Local media asset roots (user-supplied datasets; gitignored) ---
    asset_logos_dir: str = ""  # default: <repo>/nbalogos
    asset_player_images_dir: str = ""  # default: <repo>/nbaplayerimages
    # --- Kaggle historical dataset cache (kagglehub) ---
    kaggle_data_dir: str = ""  # default: kagglehub's own cache; override for CI/servers

    @property
    def logos_dir(self) -> Path:
        return (
            Path(self.asset_logos_dir) if self.asset_logos_dir else BACKEND_DIR.parent / "nbalogos"
        )

    @property
    def player_images_dir(self) -> Path:
        return (
            Path(self.asset_player_images_dir)
            if self.asset_player_images_dir
            else BACKEND_DIR.parent / "nbaplayerimages"
        )

    @property
    def contract_data_path(self) -> Path | None:
        """`CONTRACT_DATA_FILE` resolved against the repo root, not the process CWD.

        A relative path such as `data/imports/contracts/players.html` resolved
        differently depending on where the process started — it worked from the repo
        root and silently found nothing from `backend/`, which is where `make` runs
        every backend command from."""
        if not self.contract_data_file:
            return None
        candidate = Path(self.contract_data_file)
        return candidate if candidate.is_absolute() else (BACKEND_DIR.parent / candidate)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def history_season_list(self) -> list[str]:
        return [s.strip() for s in self.history_seasons.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
