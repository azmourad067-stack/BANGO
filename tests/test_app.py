from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


def test_app_value_tab_recommends_bet():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Pari à valeur" in s.value for s in at.success)


def test_app_value_tab_no_bet_when_odds_are_poor():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.number_input[2].set_value(1.70).run()  # cote bookmaker A
    assert not at.exception
    assert any("Pas de pari" in i.value for i in at.info)


def test_app_schedule_tab_lists_value_bets(monkeypatch):
    from bango.schedule import OddsApiClient, parse_events

    from .test_schedule import EVENTS

    monkeypatch.setenv("ODDS_API_KEY", "cle-de-test")
    monkeypatch.setattr(OddsApiClient, "upcoming_matches", lambda self, tour="atp", regions="eu": parse_events(EVENTS))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("1 matchs analysés, 1 pari(s) à valeur" in m.value for m in at.markdown)
    table = at.dataframe[0].value
    assert table.iloc[0]["Pari conseillé"] == "Alex de Minaur à 5.10"
    assert any("1 match(s) ignoré(s)" in c.value for c in at.caption)


def test_app_schedule_tab_asks_for_key(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("ODDS_API_KEY" in i.value for i in at.info)
