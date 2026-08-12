"""R5-4. `data_quality_issues` growth, and the scheduler that bounds it.

Measured on the development database: `asset_unmatched_player_dir` held **560 rows for
280 findings** after two `index-assets` runs, `kaggle_source_conflict` 273, and nothing
ever deleted a resolved row. Every re-derived check resolves its previous rows and writes
new ones, so a weekly job leaves fifty-two copies of every finding a year.

Two fixes, and both are tested here: findings with a stable identity are **upserted**, and
findings without one are **pruned** once they have been resolved for longer than the
retention window.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import DataQualityIssue
from app.ingestion.quality import (
    RESOLVED_RETENTION_DAYS,
    prune_resolved_issues,
    upsert_issue,
)


class TestUpsert:
    def test_a_repeated_finding_updates_rather_than_duplicates(self, db: Session):
        for run in range(5):
            upsert_issue(db, "asset_unmatched_player_dir", f"run {run}", entity="Nikola Jokić")
            db.commit()
        rows = db.query(DataQualityIssue).all()
        assert len(rows) == 1, "five runs of the same finding must leave one row"
        assert rows[0].message == "run 4"

    def test_a_resolved_finding_reopens_when_it_recurs(self, db: Session):
        issue = upsert_issue(db, "check", "first", entity="e1")
        db.commit()
        issue.resolved_at = datetime.now(UTC)
        db.commit()
        upsert_issue(db, "check", "again", entity="e1")
        db.commit()
        assert db.query(DataQualityIssue).one().resolved_at is None

    def test_different_entities_stay_separate(self, db: Session):
        upsert_issue(db, "check", "a", entity="e1")
        upsert_issue(db, "check", "b", entity="e2")
        db.commit()
        assert db.query(DataQualityIssue).count() == 2

    def test_different_checks_on_one_entity_stay_separate(self, db: Session):
        upsert_issue(db, "check_a", "a", entity="e1")
        upsert_issue(db, "check_b", "b", entity="e1")
        db.commit()
        assert db.query(DataQualityIssue).count() == 2

    def test_a_finding_with_no_entity_is_recorded_but_not_collapsed(self, db: Session):
        """Nothing stable to key on, so collapsing two would lose a distinct finding.
        These are bounded by pruning instead — and they are still *recorded*: returning an
        unattached row would drop the finding on the floor."""
        upsert_issue(db, "check", "one")
        upsert_issue(db, "check", "two")
        db.commit()
        rows = db.query(DataQualityIssue).order_by(DataQualityIssue.message).all()
        assert [r.message for r in rows] == ["one", "two"]


class TestPruning:
    def _issue(self, db: Session, resolved_days_ago: int | None) -> DataQualityIssue:
        issue = DataQualityIssue(check_name="c", severity="warning", message="m")
        if resolved_days_ago is not None:
            issue.resolved_at = datetime.now(UTC) - timedelta(days=resolved_days_ago)
        db.add(issue)
        db.commit()
        return issue

    def test_long_resolved_findings_are_deleted(self, db: Session):
        self._issue(db, resolved_days_ago=RESOLVED_RETENTION_DAYS + 5)
        assert prune_resolved_issues(db) == 1
        db.commit()
        assert db.query(DataQualityIssue).count() == 0

    def test_recently_resolved_findings_are_kept(self, db: Session):
        self._issue(db, resolved_days_ago=1)
        assert prune_resolved_issues(db) == 0

    def test_open_findings_are_never_touched(self, db: Session):
        """The one thing pruning must not do: remove something still true."""
        self._issue(db, resolved_days_ago=None)
        assert prune_resolved_issues(db, older_than_days=0) == 0
        assert db.query(DataQualityIssue).count() == 1

    def test_validate_data_prunes_as_part_of_its_sweep(self, db: Session):
        from app.ingestion.quality import validate_data

        self._issue(db, resolved_days_ago=RESOLVED_RETENTION_DAYS + 1)
        results = validate_data(db)
        assert any(r["check"] == "issue_retention" for r in results)
        assert (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.check_name == "c")
            .count()
            == 0
        )


class TestWorkerSchedule:
    def test_the_data_quality_sweep_is_scheduled(self):
        """The sweep is what actually bounds the table on a deployed instance; without a
        schedule the pruning only happens when someone runs the CLI."""
        from app.worker import build_scheduler

        scheduled = {job.args[0] for job in build_scheduler().get_jobs()}
        assert "validate_data" in scheduled
        assert {"sync_rosters", "sync_standings", "sync_contracts"} <= scheduled

    def test_every_scheduled_job_name_actually_exists(self):
        """A schedule naming a job that does not exist used to be logged as a job
        failure, which reads as an outage rather than a typo."""
        from app.worker import build_scheduler, job_map

        names = {job.args[0] for job in build_scheduler().get_jobs()}
        assert names <= set(job_map())

    def test_intervals_come_from_the_environment(self, monkeypatch):
        from app.worker import build_scheduler

        monkeypatch.setenv("SYNC_ROSTERS_EVERY_HOURS", "3")
        monkeypatch.setenv("VALIDATE_DATA_EVERY_HOURS", "12")
        by_name = {job.args[0]: job for job in build_scheduler().get_jobs()}
        assert by_name["sync_rosters"].trigger.interval == timedelta(hours=3)
        assert by_name["validate_data"].trigger.interval == timedelta(hours=12)


class TestRunJob:
    def test_an_unknown_job_is_a_configuration_error_not_a_failure(self, caplog):
        from app import worker

        with caplog.at_level("ERROR"):
            worker.run_job("sync_the_moon")
        assert any("not a known job" in record.message for record in caplog.records)

    def test_a_failing_job_is_logged_and_does_not_raise(self, monkeypatch, caplog):
        from app import worker

        def explode(_db):
            raise RuntimeError("provider down")

        monkeypatch.setattr(worker, "job_map", lambda: {"boom": explode})
        with caplog.at_level("ERROR"):
            worker.run_job("boom")
        assert any("worker job boom failed" in record.message for record in caplog.records)

    def test_a_successful_job_logs_its_row_count(self, monkeypatch, caplog):
        from app import worker

        monkeypatch.setattr(worker, "job_map", lambda: {"ok": lambda _db: 42})
        with caplog.at_level("INFO"):
            worker.run_job("ok")
        assert any("wrote 42 rows" in record.message for record in caplog.records)


class TestAssetIndexerNoLongerDuplicates:
    def test_two_index_runs_leave_one_row_per_unmatched_folder(
        self, db: Session, tmp_path, monkeypatch
    ):
        """The measured case: 560 rows for 280 findings after two runs."""
        from app.assets import indexer
        from app.config import Settings, get_settings

        players_dir = tmp_path / "photos"
        (players_dir / "Nobody At All").mkdir(parents=True)
        (players_dir / "Nobody At All" / "Image_1.png").write_bytes(b"x")
        (tmp_path / "logos").mkdir()

        get_settings.cache_clear()
        monkeypatch.setenv("ASSET_PLAYER_IMAGES_DIR", str(players_dir))
        monkeypatch.setenv("ASSET_LOGOS_DIR", str(tmp_path / "logos"))
        try:
            assert isinstance(get_settings(), Settings)
            indexer.index_assets(db)
            indexer.index_assets(db)
        finally:
            get_settings.cache_clear()

        rows = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.check_name == "asset_unmatched_player_dir")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].resolved_at is None


@pytest.mark.parametrize("days", [0, 1, RESOLVED_RETENTION_DAYS])
def test_the_retention_window_is_a_named_constant(days: int):
    assert RESOLVED_RETENTION_DAYS == 30
    assert days <= RESOLVED_RETENTION_DAYS
