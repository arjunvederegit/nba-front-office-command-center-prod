"""The provider factory must be safe to call from several threads at once.

Found in R2c browser QA, not by any test: with `CONTRACT_DATA_PROVIDER=bbref_snapshot`
set, `GET /teams/{id}/payroll` returned **500** under ordinary page load —

    ImportError: cannot import name 'BasketballReferenceSnapshotProvider'
                 from 'app.integrations.contracts.bbref_provider'

`get_contract_provider()` imports the provider module lazily, and the provider module
imported `ContractRecord` back from the package `__init__`. Single-threaded that cycle
resolves; across FastAPI's threadpool it does not — one worker holds the half-executed
provider module while another asks it for a class whose `class` statement has not run.

The defect was dormant for as long as no provider was configured, which is why every
suite was green: the lazy import never executed. These tests exercise the path a
configured provider takes.
"""

import concurrent.futures
import importlib
import sys

import pytest

PROVIDER_MODULES = [
    "app.integrations.contracts",
    "app.integrations.contracts.base",
    "app.integrations.contracts.bbref_provider",
    "app.integrations.contracts.file_provider",
]


@pytest.fixture()
def unimported_providers():
    """Force a cold import, which is the only state the race can occur in."""
    saved = {name: sys.modules.pop(name, None) for name in PROVIDER_MODULES}
    yield
    for name, module in saved.items():
        if module is not None:
            sys.modules[name] = module
        else:
            sys.modules.pop(name, None)


def test_provider_modules_do_not_import_the_package_back(unimported_providers) -> None:
    """The structural guarantee, asserted on the source: no cycle, so no race.

    Checking behaviour alone would let the cycle be reintroduced and only fail
    intermittently, which is exactly how this reached production.
    """
    from pathlib import Path

    package = Path(__file__).resolve().parents[2] / "app" / "integrations" / "contracts"
    for provider in ("bbref_provider.py", "file_provider.py"):
        source = (package / provider).read_text()
        assert "from . import" not in source, (
            f"{provider} imports from the package __init__, which lazily imports it back; "
            "import the shared types from .base instead"
        )


@pytest.mark.parametrize("provider_name", ["bbref_snapshot", "file"])
def test_concurrent_calls_all_return_a_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path, unimported_providers, provider_name: str
) -> None:
    """Eight threads entering the factory on a cold module cache, as the threadpool does."""
    from app.config import get_settings

    source = tmp_path / "contracts-source"
    source.write_text("placeholder — the factory only checks readability, never parses here")
    monkeypatch.setenv("CONTRACT_DATA_PROVIDER", provider_name)
    monkeypatch.setenv("CONTRACT_DATA_FILE", str(source))
    get_settings.cache_clear()

    module = importlib.import_module("app.integrations.contracts")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in [pool.submit(module.get_contract_provider) for _ in range(8)]]

    get_settings.cache_clear()
    assert all(provider is not None for provider in results)
    assert len({type(provider) for provider in results}) == 1


@pytest.mark.parametrize("provider_name", ["bbref_snapshot", "file"])
def test_a_configured_provider_whose_file_is_missing_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path, unimported_providers, provider_name: str
) -> None:
    """An env var alone is not a configured provider.

    `contract_provider_configured` changes what the product *says*: rules switch from
    silent to `unavailable`, and the empty state switches from "no provider is configured"
    to "the configured provider lacks these players". A typo'd path used to blame the data
    and point the operator at the wrong problem.
    """
    from app.config import get_settings

    monkeypatch.setenv("CONTRACT_DATA_PROVIDER", provider_name)
    monkeypatch.setenv("CONTRACT_DATA_FILE", str(tmp_path / "typo" / "nope.csv"))
    get_settings.cache_clear()

    module = importlib.import_module("app.integrations.contracts")
    try:
        assert module.get_contract_provider() is None
        # The intended location is still reportable, so the operator can be told which
        # path was checked rather than just that nothing was found.
        assert module.contract_source_path() is not None
    finally:
        get_settings.cache_clear()


def test_the_shared_types_are_still_importable_from_the_package() -> None:
    """`base` is an implementation detail; the package remains the public import site."""
    from app.integrations.contracts import ContractProvider, ContractRecord
    from app.integrations.contracts.base import ContractProvider as BaseProvider
    from app.integrations.contracts.base import ContractRecord as BaseRecord

    assert ContractRecord is BaseRecord
    assert ContractProvider is BaseProvider
