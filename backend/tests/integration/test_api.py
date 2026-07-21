"""Integration tests over the API with a seeded fixture database.

The app's get_db dependency is overridden to point at the test session; all records
are synthetic test fixtures (never production data)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.base import get_db
from app.db.models import PlayerSeasonStats, Standing, TeamNeed, TeamSeasonStats
from tests.conftest import make_player, make_team


@pytest.fixture()
def client(db, cap_params):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db):
    team_a = make_team(db, 1, "AAA", "Alpha Test Club")
    team_b = make_team(db, 2, "BBB", "Beta Test Club")
    players = {
        "a1": make_player(db, 101, "Fixture Alpha One", team_a, salary=20_000_000),
        "a2": make_player(db, 102, "Fixture Alpha Two", team_a, salary=5_000_000),
        "b1": make_player(db, 201, "Fixture Beta One", team_b, salary=18_000_000),
    }
    # Realistic roster sizes so roster-minimum rules don't dominate the fixtures
    for i in range(12):
        make_player(db, 300 + i, f"Fixture A Bench {i}", team_a, salary=3_000_000)
        make_player(db, 400 + i, f"Fixture B Bench {i}", team_b, salary=3_000_000)
    now = datetime.now(UTC)
    for team in (team_a, team_b):
        db.add(
            Standing(
                team_id=team.id,
                season="2025-26",
                wins=41,
                losses=41,
                win_pct=0.5,
                conference="East",
                source_retrieved_at=now,
            )
        )
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season="2025-26",
                stat_type="advanced",
                stats={
                    "OFF_RATING": 114.0,
                    "DEF_RATING": 114.0,
                    "NET_RATING": 0.0,
                    "PACE": 99.0,
                    "TS_PCT": 0.57,
                },
                source_retrieved_at=now,
            )
        )
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season="2025-26",
                stat_type="base",
                stats={"PTS": 114.0, "FG3A": 35.0, "STL": 7.5, "BLK": 5.0},
                source_retrieved_at=now,
            )
        )
        db.add(
            TeamNeed(
                team_id=team.id,
                season="2025-26",
                need_key="three_point_volume",
                severity=0.6,
                percentile=20.0,
                explanation="test fixture need",
            )
        )
    for player in players.values():
        db.add(
            PlayerSeasonStats(
                player_id=player.id,
                season="2025-26",
                stat_type="base",
                games_played=70,
                minutes=30.0,
                stats={"PTS": 18.0, "REB": 5.0, "AST": 4.0},
                source_retrieved_at=now,
            )
        )
    db.commit()
    return {"team_a": team_a, "team_b": team_b, **players}


def test_health_and_readiness(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/readiness").json()["status"] == "ready"


def test_error_format_is_deterministic(client):
    response = client.get("/api/v1/teams/nonexistent-id")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert "request_id" in body["error"]


def test_teams_and_roster(client, seeded):
    teams = client.get("/api/v1/teams").json()
    assert len(teams) == 2
    roster = client.get(f"/api/v1/teams/{seeded['team_a'].id}/roster").json()
    assert len(roster["roster"]) == 14
    assert roster["source"].startswith("NBA.com")


def test_payroll_available_with_fixture_contracts(client, seeded):
    payroll = client.get(f"/api/v1/teams/{seeded['team_a'].id}/payroll").json()
    assert payroll["payroll_available"] is True
    assert payroll["payroll"] == 20_000_000 + 5_000_000 + 12 * 3_000_000


def test_player_search_and_contract(client, seeded):
    result = client.get("/api/v1/players", params={"q": "fixture alpha"}).json()
    assert result["total"] == 2
    contract = client.get(f"/api/v1/players/{seeded['a1'].id}/contract").json()
    assert contract["available"] is True
    assert contract["years"][0]["salary"] == 20_000_000


def test_scenario_crud(client, seeded):
    created = client.post(
        "/api/v1/scenarios",
        json={"name": "Test scenario", "focal_team_id": seeded["team_a"].id, "strategy": "contend"},
    ).json()
    assert created["strategy"] == "contend"
    assert pytest.approx(sum(created["weights"].values())) == 1.0
    patched = client.patch(
        f"/api/v1/scenarios/{created['id']}", json={"strategy": "rebuild"}
    ).json()
    assert patched["strategy"] == "rebuild"


def test_validate_legal_trade_with_full_contract_data(client, seeded):
    payload = {
        "team_ids": [seeded["team_a"].id, seeded["team_b"].id],
        "player_moves": [
            {
                "player_id": seeded["a1"].id,
                "from_team_id": seeded["team_a"].id,
                "to_team_id": seeded["team_b"].id,
            },
            {
                "player_id": seeded["b1"].id,
                "from_team_id": seeded["team_b"].id,
                "to_team_id": seeded["team_a"].id,
            },
        ],
        "pick_moves": [],
    }
    result = client.post("/api/v1/trades/validate", json=payload).json()
    # salaries known and matched; minimum-team-salary warnings are fine
    matching = [r for r in result["rule_results"] if r["rule_code"] == "SALARY_MATCHING"]
    assert all(r["status"] == "pass" for r in matching)
    assert result["overall_status"] in ("verified_legal", "conditionally_valid")


def test_validate_rejects_move_to_own_team(client, seeded):
    payload = {
        "team_ids": [seeded["team_a"].id, seeded["team_b"].id],
        "player_moves": [
            {
                "player_id": seeded["a1"].id,
                "from_team_id": seeded["team_a"].id,
                "to_team_id": seeded["team_a"].id,
            },
        ],
        "pick_moves": [],
    }
    assert client.post("/api/v1/trades/validate", json=payload).status_code == 422


def test_trade_save_report_and_comparison(client, seeded):
    def trade_payload(name, out_player, in_player):
        return {
            "name": name,
            "team_ids": [seeded["team_a"].id, seeded["team_b"].id],
            "player_moves": [
                {
                    "player_id": out_player.id,
                    "from_team_id": seeded["team_a"].id,
                    "to_team_id": seeded["team_b"].id,
                },
                {
                    "player_id": in_player.id,
                    "from_team_id": seeded["team_b"].id,
                    "to_team_id": seeded["team_a"].id,
                },
            ],
            "pick_moves": [],
        }

    t1 = client.post("/api/v1/trades", json=trade_payload("Deal 1", seeded["a1"], seeded["b1"]))
    assert t1.status_code == 201
    trade1 = t1.json()
    assert trade1["legality"]["overall_status"] != "verified_illegal"
    assert seeded["team_a"].id in trade1["evaluations"]

    report = client.get(f"/api/v1/trades/{trade1['id']}/report")
    assert report.status_code == 200
    assert report.text.startswith("# Executive Trade Recommendation")
    assert "Data freshness and limitations" in report.text

    html = client.get(f"/api/v1/trades/{trade1['id']}/report", params={"format": "html"})
    assert "<title>TradeLab Executive Report</title>" in html.text

    t2 = client.post("/api/v1/trades", json=trade_payload("Deal 2", seeded["a2"], seeded["b1"]))
    comparison = client.post(
        "/api/v1/comparisons",
        json={"name": "Test comparison", "trade_ids": [trade1["id"], t2.json()["id"]]},
    ).json()
    assert len(comparison["alternatives"]) == 2
    assert "first_place_share" in comparison["sensitivity"]


def test_data_health_reports_providers(client, seeded):
    health = client.get("/api/v1/data-health").json()
    assert health["providers"]["nba_api"]["configured"] is True
    assert health["providers"]["contracts"]["configured"] is False
    assert health["tables"]["teams"]["rows"] == 2


def test_admin_sync_disabled_without_token(client):
    response = client.post("/api/v1/admin/sync")
    assert response.status_code == 403
