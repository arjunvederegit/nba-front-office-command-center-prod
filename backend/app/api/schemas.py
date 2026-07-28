"""API request/response models (Pydantic v2)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# One definition of the strategy vocabulary. It was previously inlined in
# `ScenarioIn` only, so `EvaluateRequest.strategy` and `GenerateRequest.strategy`
# were bare `str` and silently fell back to different weights on a typo (QA-7).
Strategy = Literal[
    "contend", "improve", "retool", "rebuild", "youth", "cap_relief", "custom"
]

# The report renderer only produces these two; anything else used to be accepted,
# recorded as the requested format, and then answered with markdown anyway.
ReportFormat = Literal["markdown", "html"]


class Provenance(BaseModel):
    source_provider: str = "nba_api"
    upstream: str = "NBA.com"
    source_retrieved_at: datetime | None = None


class TeamOut(BaseModel):
    id: str
    nba_team_id: int
    full_name: str
    abbreviation: str
    nickname: str | None = None
    city: str
    conference: str | None = None
    division: str | None = None
    provenance: Provenance | None = None


class RosterPlayerOut(BaseModel):
    player_id: str
    nba_player_id: int
    name: str
    position: str | None = None
    jersey_number: str | None = None
    age: float | None = None
    height_inches: int | None = None
    years_experience: int | None = None
    tei: float | None = None
    archetype: str | None = None
    availability: float | None = None


class PlayerOut(BaseModel):
    id: str
    nba_player_id: int
    full_name: str
    is_active: bool
    position: str | None = None
    birth_date: date | None = None
    height_inches: int | None = None
    weight_lbs: int | None = None
    years_experience: int | None = None
    current_team: TeamOut | None = None
    provenance: Provenance | None = None


class ScenarioWeightsIn(BaseModel):
    performance: float = Field(ge=0, default=0.22)
    fit: float = Field(ge=0, default=0.18)
    contract: float = Field(ge=0, default=0.14)
    timeline: float = Field(ge=0, default=0.16)
    assets: float = Field(ge=0, default=0.15)
    risk: float = Field(ge=0, default=0.15)


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    focal_team_id: str
    strategy: Strategy = "custom"
    horizon_years: int = Field(ge=1, le=5, default=1)
    risk_tolerance: Literal["conservative", "balanced", "aggressive"] = "balanced"
    max_added_payroll: int | None = None
    willing_to_cross_tax: bool = False
    willing_to_cross_first_apron: bool = False
    willing_to_cross_second_apron: bool = False
    untouchable_player_ids: list[str] = []
    preferred_outgoing_player_ids: list[str] = []
    positional_needs: list[str] = []
    weights: ScenarioWeightsIn = ScenarioWeightsIn()


class ScenarioPatch(BaseModel):
    name: str | None = None
    strategy: Strategy | None = None
    horizon_years: int | None = None
    risk_tolerance: str | None = None
    untouchable_player_ids: list[str] | None = None
    preferred_outgoing_player_ids: list[str] | None = None
    weights: ScenarioWeightsIn | None = None


class PlayerMove(BaseModel):
    player_id: str
    from_team_id: str
    to_team_id: str


class PickMove(BaseModel):
    from_team_id: str
    to_team_id: str
    draft_year: int = Field(ge=2026, le=2033)
    round_number: int = Field(ge=1, le=2)
    protections: str | None = None
    is_hypothetical: bool = True


class ValidateRequest(BaseModel):
    team_ids: list[str] = Field(min_length=2, max_length=3)
    player_moves: list[PlayerMove] = []
    pick_moves: list[PickMove] = []

    @field_validator("player_moves")
    @classmethod
    def moves_within_teams(cls, v: list[PlayerMove], info):
        team_ids = set(info.data.get("team_ids", []))
        for move in v:
            if move.from_team_id not in team_ids or move.to_team_id not in team_ids:
                raise ValueError("player move references a team not in the trade")
            if move.from_team_id == move.to_team_id:
                raise ValueError("player cannot be traded to their own team")
        return v


class TradeIn(ValidateRequest):
    name: str = Field(min_length=1, max_length=120)
    scenario_id: str | None = None
    notes: str | None = None


class EvaluateRequest(ValidateRequest):
    scenario_id: str | None = None
    strategy: Strategy = "custom"
    weights: ScenarioWeightsIn | None = None


class GenerateRequest(BaseModel):
    scenario_id: str | None = None
    focal_team_id: str | None = None
    strategy: Strategy = "custom"
    max_candidates: int = Field(ge=1, le=12, default=8)


class ComparisonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scenario_id: str | None = None
    trade_ids: list[str] = Field(min_length=2, max_length=5)
