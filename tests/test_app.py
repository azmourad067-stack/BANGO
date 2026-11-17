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


def test_app_schedule_tab_lists_value_bets(monkeypatch, tmp_path):
    from bango.schedule import OddsApiClient

    from .test_schedule import EVENTS, FOOTBALL, SPORTS_LIST

    monkeypatch.setenv("ODDS_API_KEY", "cle-de-test")
    monkeypatch.setenv("BANGO_SNAPSHOT", str(tmp_path / "aucun.json"))
    wta = dict(EVENTS[0], id="w1", sport_key="tennis_wta_finals", sport_title="WTA Finals")
    def later(events):  # dates dans le futur : l'application masque les matchs commencés
        return [dict(e, commence_time=e["commence_time"].replace("2026", "2099")) for e in events]

    responses = {
        "tennis_atp_paris_masters": later(EVENTS),
        "tennis_wta_finals": later([wta]),
        "soccer_france_ligue_one": later(FOOTBALL),
    }
    calls = []

    def fake_get(self, path, **params):
        calls.append(path)
        return SPORTS_LIST if path == "/sports" else responses.get(path.split("/")[2], [])

    monkeypatch.setattr(OddsApiClient, "_get", fake_get)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert not any("odds" in c for c in calls)  # rien n'est consommé avant le clic
    at.button[0].click().run()
    assert not at.exception
    assert any("3 matchs analysés, 3 pari(s) à valeur" in m.value for m in at.markdown)
    table = at.dataframe[0].value
    assert "Alex de Minaur à 5.10 (Winamax (FR))" in set(table["Pari conseillé"])
    assert set(table["Sport"]) == {"Tennis ATP", "Tennis WTA", "Football"}
    assert any("1 match(s) ignoré(s)" in c.value for c in at.caption)


def test_app_journal_tab_reads_repository_journal(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    texts = [i.value for i in at.info] + [m.label for m in at.metric]
    assert any("journal" in t.lower() or "Période suivie" in t for t in texts)


def test_app_schedule_tab_asks_for_key(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("ODDS_API_KEY" in i.value for i in at.info)


def test_app_shows_last_scan_without_spending_credits(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from bango.schedule import OddsApiClient, save_snapshot

    from .test_schedule import EVENTS, FOOTBALL

    snap = tmp_path / "latest.json"
    past = dict(EVENTS[0], id="passe", commence_time="2020-01-01T12:00:00Z")
    future = [dict(e, commence_time="2099-01-01T12:00:00Z") for e in EVENTS + FOOTBALL]
    save_snapshot(snap, [past, *future], datetime(2026, 11, 17, 16, 53, tzinfo=timezone.utc), "450")
    monkeypatch.setenv("BANGO_SNAPSHOT", str(snap))
    monkeypatch.setenv("ODDS_API_KEY", "cle-de-test")
    calls = []

    def fake_get(self, path, **params):
        calls.append(path)
        return [] if path == "/sports" else pytest.fail("aucune cote ne doit être demandée à l'ouverture")

    monkeypatch.setattr(OddsApiClient, "_get", fake_get)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert all(c == "/sports" for c in calls)  # seul l'appel gratuit
    assert any("dernier relevé automatique, le mar. 17/11 17:53" in c.value for c in at.caption)
    assert any("Requêtes restantes ce mois-ci : 450" in c.value for c in at.caption)
    assert any("2 matchs analysés, 2 pari(s) à valeur" in m.value for m in at.markdown)

    at.multiselect[0].set_value(["football"]).run()  # filtre sans appel
    assert any("1 matchs analysés" in m.value for m in at.markdown)
    assert all(c == "/sports" for c in calls)
