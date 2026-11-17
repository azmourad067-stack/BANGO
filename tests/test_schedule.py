from datetime import datetime, timedelta, timezone

import pytest

from bango import journal
from bango.cli import main
from bango.odds import fair_probabilities_n
from bango.schedule import OddsApiClient, OddsApiError, guess_surface, match_player, parse_events


def _book(key, title, prices):
    return {"key": key, "title": title, "markets": [{"key": "h2h", "outcomes": [{"name": n, "price": p} for n, p in prices.items()]}]}


# Réponses au format de l'API v4 (/sports/{sport}/odds).
EVENTS = [
    {
        "id": "e1",
        "sport_key": "tennis_atp_paris_masters",
        "sport_title": "ATP Paris Masters",
        "commence_time": "2026-11-17T13:00:00Z",
        "home_team": "Jannik Sinner",
        "away_team": "Alex de Minaur",
        "bookmakers": [
            _book("pinnacle", "Pinnacle", {"Jannik Sinner": 1.25, "Alex de Minaur": 4.30}),
            _book("winamax_fr", "Winamax (FR)", {"Jannik Sinner": 1.22, "Alex de Minaur": 5.10}),
            _book("betclic_fr", "Betclic (FR)", {"Jannik Sinner": 1.27, "Alex de Minaur": 3.90}),
        ],
    },
    {
        "id": "e2",
        "sport_key": "tennis_atp_paris_masters",
        "sport_title": "ATP Paris Masters",
        "commence_time": "2026-11-17T10:00:00Z",
        "home_team": "Joueur Sans Cotes",
        "away_team": "Autre Joueur",
        "bookmakers": [],
    },
]

FOOTBALL = [
    {
        "id": "f1",
        "sport_key": "soccer_france_ligue_one",
        "sport_title": "Ligue 1 - France",
        "commence_time": "2026-11-21T19:45:00Z",
        "home_team": "Paris Saint Germain",
        "away_team": "Lens",
        "bookmakers": [
            _book("pinnacle", "Pinnacle", {"Paris Saint Germain": 1.50, "Lens": 6.50, "Draw": 4.60}),
            _book("unibet_fr", "Unibet (FR)", {"Paris Saint Germain": 1.45, "Lens": 6.00, "Draw": 5.10}),
            _book("pmu_fr", "PMU (FR)", {"Paris Saint Germain": 1.47, "Lens": 6.20}),  # nul manquant : ignoré
        ],
    }
]


# --- Cotes à n issues -------------------------------------------------------


def test_fair_probabilities_three_way_sum_to_one():
    fair = fair_probabilities_n([1.50, 4.60, 6.50])
    assert sum(fair) == pytest.approx(1.0)
    assert fair[0] > fair[1] > fair[2]


# --- Lecture des événements ------------------------------------------------


def test_parse_tennis_events_keeps_each_bookmaker():
    matches = parse_events(EVENTS)
    m = matches[0]
    assert m.sport == "tennis" and m.tour == "atp"
    assert m.outcomes == ["Jannik Sinner", "Alex de Minaur"]
    assert m.reference.price("Alex de Minaur") == 4.30
    assert set(m.books) == {"pinnacle", "winamax_fr", "betclic_fr"}
    assert m.start.hour == 13
    assert matches[1].reference is None


def test_parse_football_three_way_and_drops_incomplete_books():
    m = parse_events(FOOTBALL)[0]
    assert m.sport == "football"
    assert m.outcomes == ["Paris Saint Germain", "Draw", "Lens"]
    assert set(m.books) == {"pinnacle", "unibet_fr"}


def test_best_odds_and_value_across_chosen_books():
    m = parse_events(EVENTS)[0]
    best = m.best_odds(["winamax_fr", "betclic_fr"])
    assert best["Jannik Sinner"].key == "betclic_fr" and best["Alex de Minaur"].key == "winamax_fr"
    res = m.assess(["winamax_fr", "betclic_fr"], min_edge=0.02)
    assert res.pick.label == "Alex de Minaur" and res.pick.bookmaker == "Winamax (FR)"
    assert parse_events(EVENTS)[1].assess(["winamax_fr"]) is None


def test_football_value_on_the_draw():
    m = parse_events(FOOTBALL)[0]
    res = m.assess(["unibet_fr", "pmu_fr"], min_edge=0.02)
    assert [s.label for s in res.sides] == ["Paris Saint Germain", "Match nul", "Lens"]
    assert res.pick is not None and res.pick.label == "Match nul"


def test_surface_and_player_matching():
    assert guess_surface("ATP French Open") == "Clay"
    assert guess_surface("ATP Wimbledon") == "Grass"
    assert guess_surface("ATP Paris Masters") == "Hard"
    known = ["Sinner J.", "De Minaur A.", "Auger-Aliassime F.", "Bautista Agut R."]
    assert match_player("Jannik Sinner", known) == "Sinner J."
    assert match_player("Alex de Minaur", known) == "De Minaur A."
    assert match_player("Félix Auger-Aliassime", known) == "Auger-Aliassime F."
    assert match_player("Roberto Bautista Agut", known) == "Bautista Agut R."
    assert match_player("Inconnu Total", known) is None


# --- Client API (réponses simulées) ----------------------------------------


class _Resp:
    def __init__(self, status, payload, headers=None):
        self.status_code, self._payload, self.headers, self.text = status, payload, headers or {}, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


SPORTS_LIST = [
    {"key": "tennis_atp_paris_masters", "group": "Tennis", "title": "ATP Paris Masters", "active": True, "has_outrights": False},
    {"key": "tennis_wta_finals", "group": "Tennis", "title": "WTA Finals", "active": True, "has_outrights": False},
    {"key": "soccer_france_ligue_one", "group": "Soccer", "title": "Ligue 1 - France", "active": True, "has_outrights": False},
    {"key": "soccer_fifa_world_cup_winner", "group": "Soccer", "title": "World Cup Winner", "active": True, "has_outrights": True},
    {"key": "basketball_nba", "group": "Basketball", "title": "NBA", "active": True, "has_outrights": False},
    {"key": "icehockey_nhl", "group": "Ice Hockey", "title": "NHL", "active": True, "has_outrights": False},
]


def test_competitions_keep_tennis_football_basket_only():
    client = OddsApiClient("cle", session=_Session([_Resp(200, SPORTS_LIST)]))
    comps = client.competitions()
    assert [c["key"] for c in comps] == [
        "tennis_atp_paris_masters", "tennis_wta_finals", "soccer_france_ligue_one", "basketball_nba",
    ]
    assert [c["sport"] for c in comps] == ["tennis", "tennis", "football", "basket"]


def test_client_asks_pinnacle_and_french_books_by_name():
    session = _Session([_Resp(200, SPORTS_LIST), _Resp(200, EVENTS, {"x-requests-remaining": "497"})])
    client = OddsApiClient("cle", session=session)
    matches = client.upcoming_matches(tour="atp")
    assert [m.id for m in matches] == ["e2", "e1"]  # triés par horaire
    url, params = session.calls[1]
    assert url.endswith("/sports/tennis_atp_paris_masters/odds")
    assert params["bookmakers"].split(",")[0] == "pinnacle" and "winamax_fr" in params["bookmakers"]
    assert len(params["bookmakers"].split(",")) <= 10  # au-delà, l'appel coûte double
    assert client.requests_remaining == "497"


def test_client_errors_are_explicit():
    with pytest.raises(OddsApiError):
        OddsApiClient("")
    client = OddsApiClient("mauvaise", session=_Session([_Resp(401, {"message": "invalid"})]))
    with pytest.raises(OddsApiError, match="Clé refusée"):
        client.competitions()


# --- Journal ---------------------------------------------------------------


def test_journal_records_once_and_updates_best_edge(tmp_path):
    path = tmp_path / "journal.csv"
    books = ["winamax_fr", "betclic_fr", "unibet_fr"]
    t0 = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)

    matches = parse_events(EVENTS + FOOTBALL)
    j, new = journal.record(matches, books, path, now=t0)
    assert new == len(j) >= 2
    assert set(j["sport"]) == {"tennis", "football"}

    better = [dict(EVENTS[0], bookmakers=[EVENTS[0]["bookmakers"][0], _book("winamax_fr", "Winamax (FR)", {"Jannik Sinner": 1.22, "Alex de Minaur": 5.40})])]
    j2, new2 = journal.record(parse_events(better), books, path, now=t0 + timedelta(hours=6))
    assert new2 == 0 and len(j2) == len(j)
    row = j2[(j2["event_id"] == "e1") & (j2["pick"] == "Alex de Minaur")].iloc[0]
    assert row["seen"] == 2 and row["odds"] == 5.40
    assert row["best_edge"] > j[(j["event_id"] == "e1") & (j["pick"] == "Alex de Minaur")].iloc[0]["best_edge"]

    reloaded = journal.load(path)
    assert len(reloaded) == len(j2) and str(reloaded["first_seen"].dt.tz) == "UTC"

    counts = journal.daily_counts(reloaded, min_edge=0.02)
    assert counts["total"].sum() == reloaded[reloaded["best_edge"] >= 0.02]["event_id"].nunique()


def test_cli_scan_writes_journal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ODDS_API_KEY", "cle")
    responses = {"/sports": SPORTS_LIST, "tennis_atp_paris_masters": EVENTS, "soccer_france_ligue_one": FOOTBALL}

    monkeypatch.setattr(OddsApiClient, "_get", lambda self, path, **p: responses["/sports"] if path == "/sports" else responses.get(path.split("/")[2], []))
    path = tmp_path / "journal.csv"
    assert main(["scan", "--journal", str(path), "--sports", "tennis", "football", "--leagues", "soccer_france_ligue_one"]) == 0
    out = capsys.readouterr().out
    assert "3 compétition(s)" in out  # 2 tournois de tennis + Ligue 1
    assert "Alex de Minaur à 5.10 chez Winamax (FR)" in out
    assert path.exists() and len(journal.load(path)) >= 2

    monkeypatch.delenv("ODDS_API_KEY")
    assert main(["scan", "--journal", str(path)]) == 1
