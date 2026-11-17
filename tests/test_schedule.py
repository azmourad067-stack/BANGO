import pytest

from bango.schedule import OddsApiClient, OddsApiError, guess_surface, match_player, parse_events

# Réponse au format de l'API v4 (/sports/{sport}/odds).
EVENTS = [
    {
        "id": "e1",
        "sport_key": "tennis_atp_paris_masters",
        "sport_title": "ATP Paris Masters",
        "commence_time": "2026-11-17T13:00:00Z",
        "home_team": "Jannik Sinner",
        "away_team": "Alex de Minaur",
        "bookmakers": [
            {"key": "pinnacle", "title": "Pinnacle", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Jannik Sinner", "price": 1.25}, {"name": "Alex de Minaur", "price": 4.30}]}]},
            {"key": "winamax_fr", "title": "Winamax (FR)", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Jannik Sinner", "price": 1.22}, {"name": "Alex de Minaur", "price": 5.10}]}]},
            {"key": "betclic", "title": "Betclic", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Jannik Sinner", "price": 1.27}, {"name": "Alex de Minaur", "price": 3.90}]}]},
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


def test_parse_events_keeps_each_bookmaker():
    matches = parse_events(EVENTS)
    m = matches[0]
    assert m.player_a == "Jannik Sinner" and m.reference.odds_b == 4.30
    assert set(m.books) == {"pinnacle", "winamax_fr", "betclic"}
    assert m.start.hour == 13
    assert matches[1].reference is None


def test_best_odds_and_value_across_chosen_books():
    m = parse_events(EVENTS)[0]
    best_a, best_b = m.best_odds(["winamax_fr", "betclic"])
    assert (best_a.key, best_b.key) == ("betclic", "winamax_fr")
    res = m.assess(["winamax_fr", "betclic"], min_edge=0.02)
    assert res.pick is not None and res.pick.label == "Alex de Minaur"
    assert parse_events(EVENTS)[1].assess(["winamax_fr"]) is None


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


def test_client_fetches_atp_tournaments_then_odds():
    sports = [
        {"key": "tennis_atp_paris_masters", "group": "Tennis", "active": True},
        {"key": "tennis_wta_finals", "group": "Tennis", "active": True},
        {"key": "soccer_france_ligue_one", "group": "Soccer", "active": True},
    ]
    session = _Session([_Resp(200, sports), _Resp(200, EVENTS, {"x-requests-remaining": "497"})])
    client = OddsApiClient("cle", session=session)
    matches = client.upcoming_matches(tour="atp")
    assert [m.id for m in matches] == ["e2", "e1"]  # triés par horaire
    assert session.calls[1][0].endswith("/sports/tennis_atp_paris_masters/odds")
    assert session.calls[1][1]["markets"] == "h2h" and session.calls[1][1]["apiKey"] == "cle"
    assert client.requests_remaining == "497"


def test_client_errors_are_explicit():
    with pytest.raises(OddsApiError):
        OddsApiClient("")
    client = OddsApiClient("mauvaise", session=_Session([_Resp(401, {"message": "invalid"})]))
    with pytest.raises(OddsApiError, match="Clé refusée"):
        client.tennis_tournaments()


def test_client_fetches_both_tours_by_default():
    sports = [
        {"key": "tennis_atp_paris_masters", "group": "Tennis", "active": True},
        {"key": "tennis_wta_finals", "group": "Tennis", "active": True},
    ]
    wta_event = dict(EVENTS[0], id="w1", sport_key="tennis_wta_finals", sport_title="WTA Finals",
                     home_team="Iga Swiatek", away_team="Coco Gauff", bookmakers=[])
    session = _Session([_Resp(200, sports), _Resp(200, EVENTS), _Resp(200, [wta_event])])
    matches = OddsApiClient("cle", session=session).upcoming_matches()
    assert {m.tour for m in matches} == {"atp", "wta"}
    assert len(session.calls) == 3
