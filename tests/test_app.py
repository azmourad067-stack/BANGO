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
