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
    #: The MODELLING window. Every served estimate — player impact, skills, the rotation
    #: allocation, the R3 conversion coefficient — is fitted and served on exactly these
    #: seasons, and R7 did not widen it.
    history_seasons: str = "2023-24,2024-25,2025-26"
    #: The seasons the historical-trade CORPUS may be described by. Deliberately a
    #: separate setting: `player_season_stats` is read by two consumers with different
    #: questions. `recency_weighted_features` collapses `history_seasons` into the window
    #: it serves; `services/comparables` scores each season on its own within-season
    #: z-scores and never collapses across them, so a 2016-17 trade can be priced without
    #: any 2016-17 number reaching a served estimate.
    #:
    #: Widening this was measured before it shipped (R7-2): the served window frame is
    #: byte-identical at 632 rows x 33 columns, and every R3 calibration figure reproduces
    #: to full float precision — 14.976967215546017, SE 1.5279397396294392,
    #: R2 0.6235734193376163 — on a season frame that grows from 1,714 rows to 5,483.
    corpus_seasons: str = (
        "2016-17,2017-18,2018-19,2019-20,2020-21,2021-22,2022-23,2023-24,2024-25,2025-26"
    )
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

    @property
    def corpus_season_list(self) -> list[str]:
        """Every season the corpus may be described by, modelling window included."""
        seasons = {s.strip() for s in self.corpus_seasons.split(",") if s.strip()}
        return sorted(seasons | set(self.history_season_list))


@lru_cache
def get_settings() -> Settings:
    return Settings()
