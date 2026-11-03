"""W2.19A. `APPLY` is the only switch between a dry run and a database write; it must fail closed.

`make activate-provider-data` (copies provider rows into the database `DATABASE_URL` names) and
`make purge-fixtures` (deletes saved analysis entities) both used to build their flag with Make's
`if` function, which is true for any non-empty value: `APPLY=0`, `APPLY=false` and `APPLY=no` all
applied. The CLI itself was always correct (`--apply` is an exact token and the default is a dry
run), so the defect lived in the Makefile, in the one place no test looked: the translation of
`APPLY` into `--apply`.

The contract pinned here, for both targets, from the command line and from the environment:

    unset, empty, 0  -> dry run (no `--apply`)
    1                -> exactly one `--apply`
    anything else    -> refused with exit status 2 before any command of the target runs

Four layers, none of which can touch a real database:

1. Static. The unsafe construction cannot come back, and `APPLY` is never expanded.
2. Make -> argv. The real Makefile is copied next to a stub interpreter that records its arguments
   and does nothing else, so the exact argument list, the exit status and "the CLI was never
   started" are observed rather than inferred from `make -n` text.
3. CLI dispatch, in process: no `--apply` selects the plan / dry-run path, `--apply` selects the
   apply path.
4. Make -> real CLI on throwaway SQLite files that the test builds inside its own temporary
   directory. The harness refuses to start unless the database is under that directory, and runs
   the commands with a from-scratch environment (nothing is inherited, so no `DATABASE_URL`, `.env`
   path or provider key of the developer can reach them).
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import cli
from app.db.models import (
    Base,
    ComparisonSet,
    Player,
    ProviderEntityId,
    Scenario,
    Team,
    TradeProposal,
    TradeTeam,
)
from app.services import provider_data_activation as act

REPO_ROOT = Path(__file__).resolve().parents[3]
MAKEFILE = REPO_ROOT / "Makefile"
MAKE = shutil.which("make")

needs_make = pytest.mark.skipif(MAKE is None, reason="GNU make is not installed")

ACTIVATE = "activate-provider-data"
PURGE = "purge-fixtures"
TARGETS = (ACTIVATE, PURGE)

UNSET: Any = object()  # APPLY is not given at all (distinct from the empty string)

#: Spellings of "do not apply" that the contract accepts.
DRY_RUN_VALUES = [UNSET, "", "0"]
#: The only spelling that applies.
APPLY_VALUE = "1"
#: Everything else is refused. Whitespace is part of the value: Make hands it over unchanged, so
#: "1 " and "0 1" must not be normalised into an accepted 1 or 0.
REFUSED_VALUES = [
    "false", "true", "no", "yes", "2", "01", "-1", "00", "10", "11", "1.0",
    "True", "TRUE", "On", "x", "1x", "x1", "xx", "x1x",
    "1 ", "0 ", "0 1", "1 1", "1\t", "1\n", "0\n", "1 0",
]
#: Leading whitespace can only be tested through the environment: on the command line Make
#: itself removes it from the value before the Makefile can see it (`APPLY=" 1"` reads as `1`).
REFUSED_ENVIRONMENT_ONLY = [" ", "\t", " 1", "\t1", " 0"]
#: Values that would do damage if they ever reached a shell or were expanded by Make.
METACHARACTER_VALUES = [
    "1; touch INJECTED",
    "1 && touch INJECTED",
    "1 || touch INJECTED",
    "1 | touch INJECTED",
    "1 > INJECTED",
    "1\ntouch INJECTED",
    "$(touch INJECTED)",
    "`touch INJECTED`",
    "$(shell touch INJECTED)",
    "${shell touch INJECTED}",
    "'; touch INJECTED; '",
    '"; touch INJECTED; "',
    "$$",
    "${APPLY}",
    "$(APPLY)",
    "*",
    "%",
    "\\",
    "1#comment",
    "1,1",  # a comma would split the arguments of a Make function it were pasted into
    ",",
    "(",
    ")",
    "1)",
]

FORMS = ("command line", "environment")


def _label(value: Any) -> str:
    return "unset" if value is UNSET else repr(value)


# ---------------------------------------------------------------------------------- 1. static

#: Make's `if` function applied to APPLY, in either bracket style: the original defect.
_UNSAFE_IF = re.compile(r"\$[({]\s*if\s+\$[({]\s*APPLY\b")
#: Any expansion of APPLY. Reading it with `$(value APPLY)` is the only permitted form: it is
#: neither expanded, split into words nor trimmed.
_APPLY_EXPANDED = re.compile(r"\$[({]\s*APPLY\s*[)}]")


def _code_lines(makefile_text: str) -> list[str]:
    return [line for line in makefile_text.splitlines() if not line.lstrip().startswith("#")]


def _apply_violations(makefile_text: str) -> list[str]:
    """Lines that test or expand APPLY in a way that is not exact."""
    return [
        line.strip()
        for line in _code_lines(makefile_text)
        if _UNSAFE_IF.search(line) or _APPLY_EXPANDED.search(line)
    ]


def _rule(makefile_text: str, target: str) -> str:
    """The header line of `target` and the tab-indented recipe lines under it."""
    lines = makefile_text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"{re.escape(target)}\s*:", line))
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        block.append(line)
    return "\n".join(block)


class TestTheUnsafeConstructCannotReturn:
    @pytest.mark.parametrize(
        "line",
        [
            "\tcd backend && .venv/bin/python -m app.cli purge-fixtures $(if $(APPLY),--apply,)",
            "\tcd backend && python -m app.cli x $(if  $(APPLY),--apply,)",
            "\tcd backend && python -m app.cli x ${if ${APPLY},--apply,}",
            "\tcd backend && python -m app.cli x $(if $(filter-out 0,$(APPLY)),--apply,)",
            "\tcd backend && python -m app.cli x $(if $(strip $(APPLY)),--apply,)",
            "\tcd backend && python -m app.cli x $(if $(APPLY:0=),--apply,)",
        ],
    )
    def test_the_check_recognises_the_original_defect_and_its_cousins(self, line: str) -> None:
        assert _apply_violations(f"target:\n{line}\n"), line

    def test_the_check_ignores_comments_and_the_unexpanded_read(self) -> None:
        sample = "# $(if $(APPLY),--apply,) is what we replaced\nx = $(findstring x$(value APPLY)x,x1x)\n"
        assert _apply_violations(sample) == []

    @pytest.mark.parametrize("target", TARGETS)
    def test_neither_target_tests_or_expands_apply(self, target: str) -> None:
        rule = _rule(MAKEFILE.read_text(encoding="utf-8"), target)
        assert _apply_violations(rule) == [], rule

    def test_nothing_in_the_makefile_tests_or_expands_apply(self) -> None:
        """A third target, or a helper, must not reintroduce the defect either."""
        assert _apply_violations(MAKEFILE.read_text(encoding="utf-8")) == []

    @pytest.mark.parametrize("target", TARGETS)
    def test_both_targets_go_through_the_shared_gate(self, target: str) -> None:
        rule = _rule(MAKEFILE.read_text(encoding="utf-8"), target)
        header, *recipe = rule.splitlines()
        prerequisites = header.split(":", 1)[1].split("##", 1)[0].split()
        assert "_apply-guard" in prerequisites, header
        assert sum("$(apply-flag)" in line for line in recipe) == 1, rule
        assert "--apply" not in rule, "the flag must come from the shared gate"


# ----------------------------------------------------------------------------- shared helpers


def _make_env(**extra: str) -> dict[str, str]:
    """A from-scratch environment: nothing of the developer's (nor MAKEFLAGS) is inherited."""
    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C", **extra}


def _run_make(
    tree: Path,
    target: str,
    *,
    apply: Any = UNSET,
    form: str = "command line",
    dry: bool = False,
    variables: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    assert MAKE is not None
    environment = _make_env(**(env or {}))
    argv = [MAKE, "--no-print-directory", "-C", str(tree)]
    if dry:
        argv.append("-n")
    argv.append(target)
    argv += [f"{k}={v}" for k, v in (variables or {}).items()]
    if apply is not UNSET:
        if form == "command line":
            argv.append(f"APPLY={apply}")
        else:
            environment["APPLY"] = apply
    return subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=180, check=False)


def _write_interpreter(tree: Path, body: str) -> None:
    interpreter = tree / "backend" / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(body, encoding="utf-8")
    interpreter.chmod(0o755)
    shutil.copy(MAKEFILE, tree / "Makefile")


@pytest.fixture()
def stub_tree(tmp_path: Path) -> tuple[Path, Path]:
    """The real Makefile beside an interpreter that only records how it was called.

    Returns (tree, call_log). Python is never started: a call is a line in the log.
    """
    tree, log = tmp_path / "stub-tree", tmp_path / "calls.log"
    _write_interpreter(
        tree,
        "#!/bin/sh\n"
        f"{{ echo CALL; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }} >> {shlex.quote(str(log))}\n"
        "exit 0\n",
    )
    return tree, log


def _calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    calls: list[list[str]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if line == "CALL":
            calls.append([])
        else:
            calls[-1].append(line)
    return calls


SOURCE = "/synthetic/source.db"  # the stub never opens it


def _expected_argv(target: str, *, apply: bool, backup_dir: str | None = None) -> list[str]:
    if target == ACTIVATE:
        argv = ["-m", "app.cli", "provider-data-activate", "--source", SOURCE]
    else:
        argv = ["-m", "app.cli", "purge-fixtures"]
    if apply:
        argv.append("--apply")
    if backup_dir and target == ACTIVATE:
        argv += ["--backup-dir", backup_dir]
    return argv


def _vars(target: str, **more: str) -> dict[str, str]:
    return ({"SOURCE": SOURCE} if target == ACTIVATE else {}) | more


# ----------------------------------------------------------------------------- 2. Make -> argv


@needs_make
@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("target", TARGETS)
class TestTheGateSelectsTheFlag:
    @pytest.mark.parametrize("value", DRY_RUN_VALUES, ids=_label)
    def test_unset_empty_and_zero_are_dry_runs(self, stub_tree, target, form, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form=form, variables=_vars(target))
        assert done.returncode == 0, done.stderr
        assert _calls(log) == [_expected_argv(target, apply=False)]

    def test_one_applies_with_exactly_one_flag(self, stub_tree, target, form) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=APPLY_VALUE, form=form, variables=_vars(target))
        assert done.returncode == 0, done.stderr
        assert _calls(log) == [_expected_argv(target, apply=True)]
        assert _calls(log)[0].count("--apply") == 1

    @pytest.mark.parametrize("value", REFUSED_VALUES, ids=_label)
    def test_every_other_value_is_refused_before_the_cli_starts(self, stub_tree, target, form, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form=form, variables=_vars(target))
        assert done.returncode == 2, (done.returncode, done.stderr)
        assert _calls(log) == [], "the interpreter must not be started for a refused value"
        assert "APPLY must be unset, empty, 0 or 1" in done.stderr
        assert "Only APPLY=1 applies" in done.stderr
        assert "Nothing was run" in done.stderr
        assert "app.cli" not in done.stdout + done.stderr, "no command may be printed"

    @pytest.mark.parametrize("value", REFUSED_VALUES, ids=_label)
    def test_a_refused_value_is_refused_by_a_dry_inspection_too(self, stub_tree, target, form, value) -> None:
        """`make -n` expands the recipe; it must not print a command for a value that is refused."""
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form=form, dry=True, variables=_vars(target))
        assert done.returncode == 2, (done.returncode, done.stderr)
        assert "app.cli" not in done.stdout
        assert _calls(log) == []

    @pytest.mark.parametrize("value", [*DRY_RUN_VALUES, APPLY_VALUE], ids=_label)
    def test_a_dry_inspection_shows_the_flag_and_runs_nothing(self, stub_tree, target, form, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form=form, dry=True, variables=_vars(target))
        assert done.returncode == 0, done.stderr
        assert done.stdout.count("--apply") == (1 if value == APPLY_VALUE else 0), done.stdout
        assert "app.cli" in done.stdout
        assert _calls(log) == [], "make -n must not execute the recipe"

    @pytest.mark.parametrize("value", METACHARACTER_VALUES, ids=_label)
    def test_metacharacters_are_refused_and_never_executed(self, stub_tree, target, form, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form=form, variables=_vars(target))
        assert done.returncode == 2, (done.returncode, done.stderr)
        assert _calls(log) == []
        assert list(tree.rglob("INJECTED")) == [], "the value was executed"
        # the value is shown back inertly, so a mistyped value can be diagnosed
        assert "APPLY must be unset, empty, 0 or 1" in done.stderr


@needs_make
@pytest.mark.parametrize("target", TARGETS)
class TestEnvironmentOnlyWhitespace:
    @pytest.mark.parametrize("value", REFUSED_ENVIRONMENT_ONLY, ids=_label)
    def test_leading_or_only_whitespace_in_the_environment_is_refused(self, stub_tree, target, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, target, apply=value, form="environment", variables=_vars(target))
        assert done.returncode == 2, (done.returncode, done.stderr)
        assert _calls(log) == []


@needs_make
class TestTheRestOfTheTargetsIsUnchanged:
    def test_a_backup_dir_and_the_source_still_reach_the_cli(self, stub_tree) -> None:
        tree, log = stub_tree
        done = _run_make(
            tree, ACTIVATE, apply="1", variables=_vars(ACTIVATE, BACKUP_DIR="/synthetic/backups")
        )
        assert done.returncode == 0, done.stderr
        assert _calls(log) == [_expected_argv(ACTIVATE, apply=True, backup_dir="/synthetic/backups")]

    @pytest.mark.parametrize("value", [*DRY_RUN_VALUES, APPLY_VALUE], ids=_label)
    def test_activation_still_requires_a_source(self, stub_tree, value) -> None:
        tree, log = stub_tree
        done = _run_make(tree, ACTIVATE, apply=value)
        assert done.returncode == 2
        assert "usage: make activate-provider-data SOURCE=" in done.stdout + done.stderr
        assert _calls(log) == []

    @pytest.mark.parametrize("apply", [UNSET, "1", "whatever"], ids=_label)
    def test_the_default_goal_is_still_help(self, stub_tree, apply) -> None:
        """The gate's rule must not become the first rule in the file, which is what a bare
        `make` runs."""
        tree, log = stub_tree
        argv = [MAKE, "--no-print-directory", "-C", str(tree)]
        env = _make_env() | ({} if apply is UNSET else {"APPLY": apply})
        bare = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60, check=False)
        listed = _run_make(tree, "help")
        assert bare.returncode == 0, bare.stderr
        assert bare.stdout == listed.stdout and ACTIVATE in bare.stdout
        assert _calls(log) == []

    def test_an_unrelated_target_is_not_blocked_by_a_stray_apply(self, stub_tree) -> None:
        """The gate guards the two writing targets only: an exported APPLY=whatever must not
        break `make help`, which also keeps the helper target out of the listing."""
        tree, _ = stub_tree
        done = _run_make(tree, "help", apply="whatever", form="environment")
        assert done.returncode == 0, done.stderr
        assert ACTIVATE in done.stdout and PURGE in done.stdout
        assert "_apply-guard" not in done.stdout


# --------------------------------------------------------------------- 3. CLI dispatch, in process


@pytest.fixture()
def activation_spies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`provider-data-activate` with both worker functions replaced by recorders."""
    target_url = f"sqlite:///{tmp_path / 'target.db'}"
    real = cli.get_settings()
    monkeypatch.setattr(cli, "get_settings", lambda: real.model_copy(update={"database_url": target_url}))
    calls: list[tuple] = []
    monkeypatch.setattr(act, "plan", lambda source, url: calls.append(("plan", source, url)) or {"mode": "dry-run"})
    monkeypatch.setattr(
        act, "apply", lambda source, url, backup: calls.append(("apply", source, url, backup)) or {"mode": "applied"}
    )
    return calls, target_url, tmp_path


def _run_cli(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int | str | None:
    monkeypatch.setattr(cli.sys, "argv", ["cli", *argv])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    return exit_info.value.code


class TestActivationDispatch:
    def test_without_apply_the_plan_path_is_selected(self, monkeypatch, activation_spies, capsys) -> None:
        calls, url, _ = activation_spies
        assert _run_cli(monkeypatch, "provider-data-activate", "--source", "/synthetic/s.db") == 0
        assert calls == [("plan", Path("/synthetic/s.db"), url)]
        assert '"mode": "dry-run"' in capsys.readouterr().out

    def test_with_apply_the_apply_path_is_selected_and_the_default_backup_sits_beside_the_target(
        self, monkeypatch, activation_spies, capsys
    ) -> None:
        calls, url, tmp = activation_spies
        assert _run_cli(monkeypatch, "provider-data-activate", "--source", "/synthetic/s.db", "--apply") == 0
        assert calls == [("apply", Path("/synthetic/s.db"), url, tmp / "backups")]
        assert '"mode": "applied"' in capsys.readouterr().out

    def test_an_explicit_backup_dir_is_used(self, monkeypatch, activation_spies) -> None:
        calls, url, tmp = activation_spies
        _run_cli(
            monkeypatch, "provider-data-activate", "--source", "/synthetic/s.db", "--apply",
            "--backup-dir", str(tmp / "elsewhere"),
        )
        assert calls == [("apply", Path("/synthetic/s.db"), url, tmp / "elsewhere")]

    @pytest.mark.parametrize("token", ["--apply=1", "--apply=0", "apply", "-apply", "--APPLY", "--apply-now", "1"])
    def test_only_the_exact_flag_applies(self, monkeypatch, activation_spies, token) -> None:
        calls, _, _ = activation_spies
        _run_cli(monkeypatch, "provider-data-activate", "--source", "/synthetic/s.db", token)
        assert [c[0] for c in calls] == ["plan"], token

    @pytest.mark.parametrize("extra", [[], ["--apply"]])
    def test_no_source_is_a_usage_error_that_calls_nothing(self, monkeypatch, activation_spies, capsys, extra) -> None:
        calls, _, _ = activation_spies
        assert _run_cli(monkeypatch, "provider-data-activate", *extra) == 2
        assert calls == []
        assert "usage: provider-data-activate" in capsys.readouterr().out

    def test_a_refusal_exits_two_and_says_nothing_was_written(self, monkeypatch, activation_spies, capsys) -> None:
        def refuse(*_args: Any) -> dict:
            raise act.ActivationRefused("synthetic refusal")

        monkeypatch.setattr(act, "apply", refuse)
        assert _run_cli(monkeypatch, "provider-data-activate", "--source", "/synthetic/s.db", "--apply") == 2
        out = capsys.readouterr().out
        assert "synthetic refusal" in out and '"nothing_was_written": true' in out


class TestPurgeDispatch:
    @pytest.fixture()
    def purge_spy(self, monkeypatch: pytest.MonkeyPatch):
        import app.ingestion.fixtures as fixtures

        class _Session:
            def __enter__(self) -> str:
                return "session"

            def __exit__(self, *exc: object) -> bool:
                return False

        calls: list[dict] = []
        monkeypatch.setattr(cli, "SessionLocal", _Session)
        monkeypatch.setattr(
            fixtures,
            "purge_fixtures",
            lambda db, *, dry_run=True: calls.append({"db": db, "dry_run": dry_run})
            or {"dry_run": dry_run, "counts": {}},
        )
        return calls

    def test_without_apply_it_is_a_dry_run(self, monkeypatch, purge_spy, capsys) -> None:
        cli_argv = ["cli", "purge-fixtures"]
        monkeypatch.setattr(cli.sys, "argv", cli_argv)
        cli.main()
        assert purge_spy == [{"db": "session", "dry_run": True}]
        assert "Dry run" in capsys.readouterr().out

    def test_with_apply_it_deletes(self, monkeypatch, purge_spy, capsys) -> None:
        monkeypatch.setattr(cli.sys, "argv", ["cli", "purge-fixtures", "--apply"])
        cli.main()
        assert purge_spy == [{"db": "session", "dry_run": False}]
        assert "Dry run" not in capsys.readouterr().out

    @pytest.mark.parametrize("token", ["--apply=1", "apply", "-apply", "--APPLY", "1"])
    def test_only_the_exact_flag_deletes(self, monkeypatch, purge_spy, token) -> None:
        monkeypatch.setattr(cli.sys, "argv", ["cli", "purge-fixtures", token])
        cli.main()
        assert [c["dry_run"] for c in purge_spy] == [True], token


# --------------------------------------------------------- 4. Make -> real CLI, throwaway databases

REVISION = "a7d3e1f9c204"
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _backend_dir() -> Path:
    """The `backend/` directory the code under test was imported from."""
    return Path(cli.__file__).resolve().parents[1]


def _require_disposable(db_path: Path, root: Path) -> str:
    """Refuse to start unless the database is a file under this test's own directory."""
    resolved = db_path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise AssertionError(f"{resolved} is not under the test's temporary directory {root}")
    return f"sqlite:///{resolved}"


@pytest.fixture()
def real_cli_tree(tmp_path: Path) -> Path:
    """The real Makefile beside an interpreter that starts the real `app.cli` from this checkout."""
    tree = tmp_path / "cli-tree"
    _write_interpreter(
        tree,
        "#!/bin/sh\n"
        f"PYTHONPATH={shlex.quote(str(_backend_dir()))} exec {shlex.quote(sys.executable)} -B \"$@\"\n",
    )
    return tree


def _run_real(tree: Path, root: Path, db: Path, target: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    url = _require_disposable(db, root)
    env = {
        "DATABASE_URL": url,
        "ROSTERLAB_OFFLINE": "1",
        "CURRENT_SEASON": "2025-26",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return _run_make(tree, target, env=env, **kwargs)


def _report(stdout: str) -> dict:
    lines = stdout.splitlines()
    starts = [i for i, line in enumerate(lines) if line == "{"]
    assert starts, stdout
    return json.JSONDecoder().raw_decode("\n".join(lines[starts[-1] :]))[0]


def _snapshot(folder: Path) -> dict[str, str]:
    """Every path under `folder` with the sha256 of each file: detects any write or new directory."""
    out: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        key = str(path.relative_to(folder))
        out[key] = "<dir>" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by 1")]
        return {n: con.execute(f'select count(*) from "{n}"').fetchone()[0] for n in names}
    finally:
        con.close()


def _new_database(path: Path, *, revision: str | None = REVISION) -> str:
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    if revision:
        with engine.begin() as conn:
            conn.execute(text("create table alembic_version (version_num varchar(32) not null)"))
            conn.execute(text("insert into alembic_version values (:r)"), {"r": revision})
    engine.dispose()
    return url


def _seed_core(url: str) -> None:
    engine = create_engine(url)
    with Session(engine) as db:
        db.add(Team(id="t1", nba_team_id=1, full_name="Alpha", abbreviation="AAA", nickname="A", city="A"))
        db.add(Player(id="p1", nba_player_id=11, full_name="Player One", is_active=True))
        db.commit()
    engine.dispose()


def _link(row_id: str, provider_id: str, internal_id: str, entity_type: str) -> ProviderEntityId:
    return ProviderEntityId(
        id=row_id, entity_type=entity_type, provider="balldontlie", provider_id=provider_id,
        internal_id=internal_id, match_method="x", confidence="high", evidence={}, observed_at=NOW,
    )


@pytest.fixture()
def databases(tmp_path: Path) -> SimpleNamespace:
    """A synthetic source holding two provider links and a synthetic target that lacks them."""
    data = tmp_path / "data"
    data.mkdir()
    source, target = data / "source.db", data / "target.db"
    for url in (_new_database(source), _new_database(target)):
        _seed_core(url)
    engine = create_engine(f"sqlite:///{source}")
    with Session(engine) as db:
        db.add_all([_link("pe1", "9", "p1", "player"), _link("pe2", "3", "t1", "team")])
        db.commit()
    engine.dispose()
    return SimpleNamespace(root=tmp_path, data=data, source=source, target=target, backups=data / "backups")


@needs_make
class TestProviderActivationOnThrowawayDatabases:
    def _activate(self, tree, db, apply, form="command line", **extra):
        return _run_real(
            tree, db.root, db.target, ACTIVATE, apply=apply, form=form,
            variables={"SOURCE": str(db.source), "BACKUP_DIR": str(db.backups), **extra},
        )

    @pytest.mark.parametrize(("value", "form"), [(UNSET, "command line"), ("", "command line"), ("0", "command line"), ("0", "environment")], ids=_label)
    def test_unset_empty_and_zero_change_nothing_and_create_no_backup(self, real_cli_tree, databases, value, form) -> None:
        before = _snapshot(databases.data)
        done = self._activate(real_cli_tree, databases, value, form)
        assert done.returncode == 0, done.stdout + done.stderr
        report = _report(done.stdout)
        assert report["mode"] == "dry-run" and report["total_to_add"] == 2
        assert _snapshot(databases.data) == before, "a dry run wrote or created something"
        assert not databases.backups.exists()

    def test_one_applies_after_a_verified_backup_and_touches_only_the_allow_list(self, real_cli_tree, databases) -> None:
        target_before = _counts(databases.target)
        done = self._activate(real_cli_tree, databases, "1")
        assert done.returncode == 0, done.stdout + done.stderr
        report = _report(done.stdout)
        assert report["mode"] == "applied"
        assert report["written"]["provider_entity_ids"] == 2
        assert report["untouched_tables_identical"] is True
        after = _counts(databases.target)
        assert after["provider_entity_ids"] == 2
        assert {t: n for t, n in after.items() if t != "provider_entity_ids"} == {
            t: n for t, n in target_before.items() if t != "provider_entity_ids"
        }
        # the backup exists, passes SQLite's own check, and holds the state from before the write
        [backup] = sorted(databases.backups.glob("*.db"))
        assert report["backup"]["path"] == str(backup) and report["backup"]["integrity_check"] == "ok"
        con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        try:
            assert con.execute("pragma integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()
        assert _counts(backup) == target_before

    @pytest.mark.parametrize("form", FORMS)
    @pytest.mark.parametrize("value", ["false", "yes", "2", "1 ", "$(shell touch INJECTED)", "1; touch INJECTED"])
    def test_invalid_values_never_reach_the_cli_or_the_database(self, real_cli_tree, databases, value, form) -> None:
        before = _snapshot(databases.data)
        done = self._activate(real_cli_tree, databases, value, form)
        assert done.returncode == 2
        assert "APPLY must be unset, empty, 0 or 1" in done.stderr
        assert done.stdout == "", "the CLI printed something, so it started"
        assert _snapshot(databases.data) == before
        assert not databases.backups.exists()
        assert list(databases.root.rglob("INJECTED")) == []

    def test_the_backup_and_integrity_safeguards_still_refuse_before_any_write(self, real_cli_tree, databases) -> None:
        # a target one migration behind the source: refused, nothing written, no backup taken
        con = sqlite3.connect(databases.target)
        con.execute("update alembic_version set version_num='older'")
        con.commit()
        con.close()
        before = _snapshot(databases.data)
        done = self._activate(real_cli_tree, databases, "1")
        assert done.returncode == 2
        assert "schema revisions differ" in done.stdout and '"nothing_was_written": true' in done.stdout
        assert _snapshot(databases.data) == before
        assert not databases.backups.exists()

    def test_a_conflicting_row_blocks_the_apply_before_any_backup_or_write(self, real_cli_tree, databases) -> None:
        engine = create_engine(f"sqlite:///{databases.target}")
        with Session(engine) as db:  # same id as a source row, different content
            db.add(_link("pe1", "999", "p1", "player"))
            db.commit()
        engine.dispose()
        before = _snapshot(databases.data)
        done = self._activate(real_cli_tree, databases, "1")
        assert done.returncode == 2
        assert "conflicting or dangling rows" in done.stdout
        assert _snapshot(databases.data) == before
        assert not databases.backups.exists()


def _seed_fixture_entities(url: str) -> None:
    """Three automated-looking entities (and what hangs off them) beside three that must survive."""
    engine = create_engine(url)
    with Session(engine) as db:
        db.add(Team(id="t1", nba_team_id=1, full_name="Alpha", abbreviation="AAA", nickname="A", city="A"))
        db.add(Scenario(name="E2E scenario", focal_team_id="t1", strategy="contend"))
        db.add(Scenario(name="Contend now", focal_team_id="t1", strategy="contend"))
        fixture, keeper = TradeProposal(name="E2E synthetic deal"), TradeProposal(name="Real swap")
        db.add_all([fixture, keeper])
        db.flush()
        db.add(TradeTeam(trade_id=fixture.id, team_id="t1"))
        db.add(TradeTeam(trade_id=keeper.id, team_id="t1"))
        db.add(ComparisonSet(name="probe", trade_ids=[fixture.id, keeper.id]))
        db.add(ComparisonSet(name="Shortlist", trade_ids=[keeper.id]))
        db.commit()
    engine.dispose()


@pytest.fixture()
def fixture_db(tmp_path: Path) -> SimpleNamespace:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "dev.db"
    _seed_fixture_entities(_new_database(path, revision=None))
    return SimpleNamespace(root=tmp_path, data=data, path=path)


def _names(path: Path) -> dict[str, list[str]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            table: sorted(r[0] for r in con.execute(f"select name from {table}"))
            for table in ("scenarios", "trade_proposals", "comparison_sets")
        }
    finally:
        con.close()


@needs_make
class TestFixtureDeletionOnThrowawayDatabases:
    def _purge(self, tree, db, apply, form="command line"):
        return _run_real(tree, db.root, db.path, PURGE, apply=apply, form=form)

    @pytest.mark.parametrize(("value", "form"), [(UNSET, "command line"), ("", "command line"), ("0", "command line"), ("0", "environment")], ids=_label)
    def test_unset_empty_and_zero_preserve_every_record(self, real_cli_tree, fixture_db, value, form) -> None:
        before_files, before_counts = _snapshot(fixture_db.data), _counts(fixture_db.path)
        done = self._purge(real_cli_tree, fixture_db, value, form)
        assert done.returncode == 0, done.stdout + done.stderr
        assert _report(done.stdout)["dry_run"] is True
        assert _report(done.stdout)["counts"] == {"scenarios": 1, "trades": 1, "comparisons": 1}
        assert "Dry run" in done.stdout
        assert _counts(fixture_db.path) == before_counts
        assert _snapshot(fixture_db.data) == before_files

    def test_one_deletes_only_the_fixture_entities(self, real_cli_tree, fixture_db) -> None:
        done = self._purge(real_cli_tree, fixture_db, "1")
        assert done.returncode == 0, done.stdout + done.stderr
        assert _report(done.stdout)["dry_run"] is False and "Dry run" not in done.stdout
        assert _names(fixture_db.path) == {
            "scenarios": ["Contend now"],
            "trade_proposals": ["Real swap"],
            "comparison_sets": ["Shortlist"],
        }
        counts = _counts(fixture_db.path)
        assert counts["trade_teams"] == 1 and counts["teams"] == 1, "only what hangs off the fixtures goes"

    @pytest.mark.parametrize("form", FORMS)
    @pytest.mark.parametrize("value", ["false", "no", "2", "0 1", "$(shell touch INJECTED)", "1; touch INJECTED"])
    def test_invalid_values_never_reach_the_cli_or_the_records(self, real_cli_tree, fixture_db, value, form) -> None:
        before = _snapshot(fixture_db.data)
        done = self._purge(real_cli_tree, fixture_db, value, form)
        assert done.returncode == 2
        assert "APPLY must be unset, empty, 0 or 1" in done.stderr
        assert done.stdout == ""
        assert _snapshot(fixture_db.data) == before
        assert list(fixture_db.root.rglob("INJECTED")) == []


class TestTheHarnessRefusesAnythingThatIsNotThrowaway:
    def test_a_database_outside_the_temporary_directory_is_rejected(self, tmp_path: Path) -> None:
        elsewhere = Path(__file__).resolve().parent / "not-a-throwaway.db"
        with pytest.raises(AssertionError, match="not under the test's temporary directory"):
            _require_disposable(elsewhere, tmp_path)

    def test_a_database_inside_it_is_accepted(self, tmp_path: Path) -> None:
        assert _require_disposable(tmp_path / "x.db", tmp_path).startswith("sqlite:///")
