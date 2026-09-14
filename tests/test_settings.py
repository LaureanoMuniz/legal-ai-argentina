from pathlib import Path

import pytest

from legal_ai.settings import Settings


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)


def test_defaults_point_to_local_data_dir(monkeypatch):
    monkeypatch.delenv("LEGAL_AI_DATA_DIR", raising=False)
    settings = Settings()
    assert settings.data_dir == Path("data")
    assert settings.infoleg_min_interval_seconds == 0.0
    assert settings.infoleg_workers == 8
    assert "Mozilla/5.0" in settings.infoleg_user_agent


def test_env_overrides_data_dir(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_DATA_DIR", "/tmp/somewhere")
    settings = Settings()
    assert settings.data_dir == Path("/tmp/somewhere")
