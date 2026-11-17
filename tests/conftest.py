"""Shared test isolation."""
import pytest

from src.api.config import settings


@pytest.fixture(autouse=True)
def isolated_imerg_store(tmp_path_factory, monkeypatch):
    """Tests never read the developer's real IMERG store or contact NASA."""
    monkeypatch.setattr(settings, "IMERG_EARLY_STORE", str(tmp_path_factory.mktemp("imerg_early")))
    monkeypatch.setattr(settings, "IMERG_EARLY_ENABLED", False)
    # Outlook tests are deterministic without the trained package; Stage 2 tests pass a model explicitly.
    monkeypatch.setattr(settings, "STAGE2_MODEL_ENABLED", False)
    # The developer's .env may enable hourly collection; tests never start it or reach providers.
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_AUTOMATED", False)
    monkeypatch.setattr(settings, "MONITORING_POINT_COLLECTION_INTERVAL_HOURS", 1)
