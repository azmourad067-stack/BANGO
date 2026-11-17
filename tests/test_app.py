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
    wta = dict(EVENTS[0], id="w1", sport_key="tennis_wta_finals", sport_title="WTA Finals")
    monkeypatch.setattr(OddsApiClient, "upcoming_matches", lambda self, tour=None, regions="eu": parse_events([*EVENTS, wta]))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("2 matchs analysés, 2 pari(s) à valeur" in m.value for m in at.markdown)
    table = at.dataframe[0].value
    assert table.iloc[0]["Pari conseillé"] == "Alex de Minaur à 5.10"
    assert set(table["Circuit"]) == {"ATP", "WTA"}
    assert any("1 match(s) ignoré(s)" in c.value for c in at.caption)


def test_app_schedule_tab_asks_for_key(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("ODDS_API_KEY" in i.value for i in at.info)
