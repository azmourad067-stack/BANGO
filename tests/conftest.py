import pytest


@pytest.fixture(autouse=True)
def _no_repository_snapshot(monkeypatch, tmp_path):
    """Les tests n'utilisent jamais le relevé réel enregistré dans data/latest.json."""
    monkeypatch.setenv("BANGO_SNAPSHOT", str(tmp_path / "aucun-releve.json"))
