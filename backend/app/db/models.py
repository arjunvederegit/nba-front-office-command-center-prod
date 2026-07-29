"""Normalized TradeLab schema.

Conventions
- Internal primary keys are UUID strings; external provider identifiers (NBA.com team
  and player IDs) are separate unique columns so identity reconciliation never leaks
  provider IDs into domain relationships.
- Every provider-derived table carries provenance columns (ProvenanceMixin): which
  provider, which upstream record, and when it was retrieved. `valid_from`/`valid_to`
  support snapshot semantics — rows are superseded, not silently overwritten.
- Wide statistical payloads keep their full normalized row in a JSON `stats` column in
  addition to first-class columns used by models and the API.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def uuid_pk() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProvenanceMixin(TimestampMixin):
    source_provider: Mapped[str] = mapped_column(String(50), default="nba_api")
    source_record_id: Mapped[str | None] = mapped_column(String(100))
    source_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingestion_run_id: Mapped[str | None] = mapped_column(String(36))


# --------------------------------------------------------------------------- identity


class Team(Base, ProvenanceMixin):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    nba_team_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    abbreviation: Mapped[str] = mapped_column(String(10), index=True)
    nickname: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50))
    state: Mapped[str | None] = mapped_column(String(50))
    year_founded: Mapped[int | None] = mapped_column(Integer)
    conference: Mapped[str | None] = mapped_column(String(10))
    division: Mapped[str | None] = mapped_column(String(20))


class Player(Base, ProvenanceMixin):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    nba_player_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100), index=True)
    first_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    birth_date: Mapped[date | None] = mapped_column(Date)
    height_inches: Mapped[int | None] = mapped_column(Integer)
    weight_lbs: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(20))
    years_experience: Mapped[int | None] = mapped_column(Integer)
    draft_year: Mapped[int | None] = mapped_column(Integer)
    draft_round: Mapped[int | None] = mapped_column(Integer)
    draft_number: Mapped[int | None] = mapped_column(Integer)


class PlayerTeamHistory(Base, ProvenanceMixin):
    """Observed player→team assignments over time (from roster snapshots)."""

    __tablename__ = "player_team_history"
    __table_args__ = (Index("ix_pth_player_season", "player_id", "season"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    season: Mapped[str] = mapped_column(String(10))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RosterEntry(Base, ProvenanceMixin):
    """Current roster snapshot rows (one active snapshot per season; superseded rows get valid_to)."""

    __tablename__ = "rosters"
    __table_args__ = (
        UniqueConstraint("team_id", "player_id", "season", "valid_from", name="uq_roster_entry"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    jersey_number: Mapped[str | None] = mapped_column(String(10))
    position: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[float | None] = mapped_column(Float)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    player: Mapped[Player] = relationship(lazy="joined")
    team: Mapped[Team] = relationship(lazy="joined")


# ----------------------------------------------------------------------------- games


class Game(Base, ProvenanceMixin):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    nba_game_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    home_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="final")


class PlayerGameStats(Base, ProvenanceMixin):
    __tablename__ = "player_game_stats"
    __table_args__ = (UniqueConstraint("game_id", "player_id", name="uq_pgs"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    minutes: Mapped[float | None] = mapped_column(Float)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)


class PlayerSeasonStats(Base, ProvenanceMixin):
    __tablename__ = "player_season_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season", "stat_type", name="uq_pss"),
        Index("ix_pss_season", "season", "stat_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    season: Mapped[str] = mapped_column(String(10))
    stat_type: Mapped[str] = mapped_column(String(20))  # base | advanced | estimated
    games_played: Mapped[int | None] = mapped_column(Integer)
    minutes: Mapped[float | None] = mapped_column(Float)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    player: Mapped[Player] = relationship(lazy="joined")


class TeamSeasonStats(Base, ProvenanceMixin):
    __tablename__ = "team_season_stats"
    __table_args__ = (UniqueConstraint("team_id", "season", "stat_type", name="uq_tss"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    stat_type: Mapped[str] = mapped_column(String(20))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    team: Mapped[Team] = relationship(lazy="joined")


class Standing(Base, ProvenanceMixin):
    __tablename__ = "standings"
    __table_args__ = (UniqueConstraint("team_id", "season", name="uq_standing"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    wins: Mapped[int] = mapped_column(Integer)
    losses: Mapped[int] = mapped_column(Integer)
    win_pct: Mapped[float] = mapped_column(Float)
    conference: Mapped[str | None] = mapped_column(String(10))
    conference_rank: Mapped[int | None] = mapped_column(Integer)
    playoff_rank: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    team: Mapped[Team] = relationship(lazy="joined")


# ------------------------------------------------------------------- contracts / caps


class Contract(Base, ProvenanceMixin):
    """Contract header from an optional non-nba_api provider. Absent unless configured."""

    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    # Nullable: NULL means the provider does not report contract type. A default of
    # "standard" asserted that every contract was standard, which flipped ROSTER_SIZE
    # from (warning, medium) to (pass, high) on data nobody had (C9).
    contract_type: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    signed_date: Mapped[date | None] = mapped_column(Date)
    no_trade_clause: Mapped[bool | None] = mapped_column(Boolean)
    source_name: Mapped[str] = mapped_column(String(100))
    source_date: Mapped[date | None] = mapped_column(Date)

    years: Mapped[list["ContractYear"]] = relationship(back_populates="contract", lazy="selectin")


class ContractYear(Base, ProvenanceMixin):
    __tablename__ = "contract_years"
    __table_args__ = (UniqueConstraint("contract_id", "season", name="uq_contract_year"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    salary: Mapped[int] = mapped_column(Integer)
    guaranteed: Mapped[int | None] = mapped_column(Integer)
    player_option: Mapped[bool | None] = mapped_column(Boolean)
    team_option: Mapped[bool | None] = mapped_column(Boolean)

    contract: Mapped[Contract] = relationship(back_populates="years")


class Injury(Base, ProvenanceMixin):
    """Populated only when an injury provider is configured. Never fabricated."""

    __tablename__ = "injuries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base, ProvenanceMixin):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[date | None] = mapped_column(Date)


class DraftPick(Base, ProvenanceMixin):
    """Verified pick ownership requires an authoritative provider; hypothetical picks
    used in trade construction live in trade_assets with is_hypothetical=True."""

    __tablename__ = "draft_picks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    original_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    owning_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    draft_year: Mapped[int] = mapped_column(Integer)
    round_number: Mapped[int] = mapped_column(Integer)
    protections: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class LeagueCapParameters(Base, TimestampMixin):
    """Official league-year cap figures loaded from version-controlled YAML."""

    __tablename__ = "league_cap_parameters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    league_year: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    salary_cap: Mapped[int] = mapped_column(Integer)
    luxury_tax: Mapped[int] = mapped_column(Integer)
    first_apron: Mapped[int] = mapped_column(Integer)
    second_apron: Mapped[int] = mapped_column(Integer)
    minimum_team_salary: Mapped[int] = mapped_column(Integer)
    effective_date: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    extras: Mapped[dict] = mapped_column(JSON, default=dict)


# ------------------------------------------------------------------ data engineering


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    upstream: Mapped[str] = mapped_column(String(100))
    package_version: Mapped[str | None] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class DataSyncRun(Base, TimestampMixin):
    __tablename__ = "data_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    job_name: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|succeeded|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class DataQualityIssue(Base, TimestampMixin):
    __tablename__ = "data_quality_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    check_name: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    entity: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ----------------------------------------------------------------------------- models


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    # A version string must identify a model. Before R1-9 it was a training-run
    # timestamp, so all three models trained in one run shared `v202607210204` and the
    # table held it three times per model. Versions are content hashes now, and the
    # constraint keeps them that way.
    __table_args__ = (UniqueConstraint("model_name", "version", name="uq_model_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    model_name: Mapped[str] = mapped_column(String(50), index=True)
    version: Mapped[str] = mapped_column(String(30))
    algorithm: Mapped[str] = mapped_column(String(50))
    training_period: Mapped[str | None] = mapped_column(String(50))
    feature_list: Mapped[list] = mapped_column(JSON, default=list)
    target: Mapped[str | None] = mapped_column(String(100))
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(String(300))
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_commit: Mapped[str | None] = mapped_column(String(50))
    data_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class PlayerImpactEstimate(Base, TimestampMixin):
    __tablename__ = "player_impact_estimates"
    __table_args__ = (UniqueConstraint("player_id", "season", "model_version_id", name="uq_pie"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    tei: Mapped[float] = mapped_column(Float)  # TradeLab Estimated Impact, per-100 scale
    tei_offense: Mapped[float | None] = mapped_column(Float)
    tei_defense: Mapped[float | None] = mapped_column(Float)
    tei_low: Mapped[float | None] = mapped_column(Float)  # bootstrap 10th percentile
    tei_high: Mapped[float | None] = mapped_column(Float)  # bootstrap 90th percentile
    availability: Mapped[float | None] = mapped_column(Float)  # 0..1 weighted GP share
    minutes_estimate: Mapped[float | None] = mapped_column(Float)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)

    player: Mapped[Player] = relationship(lazy="joined")


class PlayerArchetype(Base, TimestampMixin):
    __tablename__ = "player_archetypes"
    __table_args__ = (UniqueConstraint("player_id", "season", name="uq_archetype"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    season: Mapped[str] = mapped_column(String(10))
    cluster_id: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(50))
    distances: Mapped[dict] = mapped_column(JSON, default=dict)


class TeamNeed(Base, TimestampMixin):
    __tablename__ = "team_needs"
    __table_args__ = (UniqueConstraint("team_id", "season", "need_key", name="uq_team_need"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(10))
    need_key: Mapped[str] = mapped_column(String(50))
    severity: Mapped[float] = mapped_column(Float)  # 0..1
    percentile: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)


# -------------------------------------------------------------------------- scenarios


class Scenario(Base, TimestampMixin):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    name: Mapped[str] = mapped_column(String(120))
    focal_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    strategy: Mapped[str] = mapped_column(String(60))
    horizon_years: Mapped[int] = mapped_column(Integer, default=1)
    risk_tolerance: Mapped[str] = mapped_column(String(20), default="balanced")
    max_added_payroll: Mapped[int | None] = mapped_column(Integer)
    willing_to_cross_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    willing_to_cross_first_apron: Mapped[bool] = mapped_column(Boolean, default=False)
    willing_to_cross_second_apron: Mapped[bool] = mapped_column(Boolean, default=False)
    untouchable_player_ids: Mapped[list] = mapped_column(JSON, default=list)
    preferred_outgoing_player_ids: Mapped[list] = mapped_column(JSON, default=list)
    positional_needs: Mapped[list] = mapped_column(JSON, default=list)
    min_retained_first_round_picks: Mapped[int | None] = mapped_column(Integer)

    focal_team: Mapped[Team] = relationship(lazy="joined")
    weights: Mapped[list["ScenarioWeight"]] = relationship(
        back_populates="scenario", lazy="selectin", cascade="all, delete-orphan"
    )


class ScenarioWeight(Base, TimestampMixin):
    __tablename__ = "scenario_weights"
    __table_args__ = (UniqueConstraint("scenario_id", "component", name="uq_scenario_weight"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    component: Mapped[str] = mapped_column(
        String(30)
    )  # performance|fit|contract|timeline|assets|risk
    weight: Mapped[float] = mapped_column(Float)

    scenario: Mapped[Scenario] = relationship(back_populates="weights")


# ----------------------------------------------------------------------------- trades


class TradeProposal(Base, TimestampMixin):
    __tablename__ = "trade_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[str | None] = mapped_column(Text)

    teams: Mapped[list["TradeTeam"]] = relationship(
        back_populates="trade", lazy="selectin", cascade="all, delete-orphan"
    )
    assets: Mapped[list["TradeAsset"]] = relationship(
        back_populates="trade", lazy="selectin", cascade="all, delete-orphan"
    )


class TradeTeam(Base, TimestampMixin):
    __tablename__ = "trade_teams"
    __table_args__ = (UniqueConstraint("trade_id", "team_id", name="uq_trade_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))

    trade: Mapped[TradeProposal] = relationship(back_populates="teams")
    team: Mapped[Team] = relationship(lazy="joined")


class TradeAsset(Base, TimestampMixin):
    __tablename__ = "trade_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(20))  # player | pick
    from_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    to_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    draft_year: Mapped[int | None] = mapped_column(Integer)
    round_number: Mapped[int | None] = mapped_column(Integer)
    protections: Mapped[str | None] = mapped_column(String(200))
    is_hypothetical: Mapped[bool] = mapped_column(Boolean, default=False)

    trade: Mapped[TradeProposal] = relationship(back_populates="assets")
    player: Mapped[Player | None] = relationship(lazy="joined")


class TradeRuleResult(Base, TimestampMixin):
    __tablename__ = "trade_rule_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(60))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(20))  # pass|fail|warning|unavailable
    message: Mapped[str] = mapped_column(Text)
    calculation: Mapped[dict] = mapped_column(JSON, default=dict)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    confidence: Mapped[str] = mapped_column(String(10), default="high")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradeEvaluation(Base, TimestampMixin):
    __tablename__ = "trade_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    legality_status: Mapped[str] = mapped_column(String(30))
    composite_utility: Mapped[float | None] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[dict] = mapped_column(JSON, default=dict)
    sensitivity: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    data_version: Mapped[str | None] = mapped_column(String(30))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ComparisonSet(Base, TimestampMixin):
    __tablename__ = "comparison_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"))
    name: Mapped[str] = mapped_column(String(120))
    trade_ids: Mapped[list] = mapped_column(JSON, default=list)


class GeneratedReport(Base, TimestampMixin):
    __tablename__ = "generated_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trade_proposals.id"), index=True)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"))
    format: Mapped[str] = mapped_column(String(10), default="markdown")
    content: Mapped[str] = mapped_column(Text)
    llm_enhanced: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaAsset(Base, ProvenanceMixin):
    """Asset manifest for user-supplied local images (player photos, team logos).

    Files stay outside git and outside the frontend bundle; the backend serves them
    by stable NBA id with deterministic fallbacks. `match_method`/`confidence`
    record how a name-keyed file was resolved to an identity — unmatched files are
    kept for review, never guessed into a player."""

    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("entity_type", "file_path", name="uq_media_asset_path"),
        Index("ix_media_entity", "entity_type", "nba_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    entity_type: Mapped[str] = mapped_column(String(20))  # player | team
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    nba_id: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))  # relative to the asset root dir
    content_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    match_method: Mapped[str] = mapped_column(
        String(30)
    )  # nba_id|exact_name|normalized_name|abbreviation|manual
    confidence: Mapped[str] = mapped_column(String(20), default="high")  # high|medium|unmatched
    source_label: Mapped[str] = mapped_column(String(100))  # e.g. folder name the file came from
    alt_text: Mapped[str] = mapped_column(String(200))
