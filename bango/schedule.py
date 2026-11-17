"""Programme des matchs à venir et cotes en direct via The Odds API (https://the-odds-api.com).

Une clé gratuite (environ 500 requêtes par mois) suffit pour un usage personnel.
Chaque appel de cotes coûte 1 requête par tournoi et par région : le programme
complet d'une semaine de tennis consomme donc quelques requêtes seulement.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from .value import ValueAssessment, assess_value

API_URL = "https://api.the-odds-api.com/v4"
REFERENCE_BOOK = "pinnacle"

# Mots repérés dans le nom du tournoi pour en déduire la surface.
CLAY_WORDS = (
    "french open", "roland", "monte carlo", "madrid", "rome", "italian open", "barcelona", "hamburg",
    "estoril", "munich", "geneva", "lyon", "buenos aires", "rio", "santiago", "houston", "marrakech",
    "bastad", "gstaad", "umag", "kitzbuhel", "bucharest", "cordoba",
)
GRASS_WORDS = ("wimbledon", "queen", "halle", "eastbourne", "s-hertogenbosch", "stuttgart", "mallorca", "newport")


@dataclass
class BookOdds:
    key: str
    title: str
    odds_a: float
    odds_b: float


@dataclass
class UpcomingMatch:
    id: str
    tournament: str
    sport_key: str
    start: datetime
    player_a: str
    player_b: str
    books: dict[str, BookOdds] = field(default_factory=dict)

    @property
    def tour(self) -> str:
        return "wta" if self.sport_key.startswith("tennis_wta") else "atp"

    @property
    def surface(self) -> str:
        return guess_surface(self.tournament)

    @property
    def reference(self) -> BookOdds | None:
        return self.books.get(REFERENCE_BOOK)

    def best_odds(self, book_keys: list[str]) -> tuple[BookOdds | None, BookOdds | None]:
        """Meilleure cote pour chaque joueur parmi les bookmakers choisis."""
        pool = [b for k, b in self.books.items() if k in book_keys]
        best_a = max(pool, key=lambda b: b.odds_a, default=None)
        best_b = max(pool, key=lambda b: b.odds_b, default=None)
        return best_a, best_b

    def assess(self, book_keys: list[str], min_edge: float = 0.02, bankroll: float = 1000.0) -> ValueAssessment | None:
        ref = self.reference
        best_a, best_b = self.best_odds(book_keys)
        if ref is None or best_a is None or best_b is None:
            return None
        return assess_value(
            ref.odds_a, ref.odds_b, best_a.odds_a, best_b.odds_b,
            min_edge=min_edge, bankroll=bankroll, labels=(self.player_a, self.player_b),
        )


class OddsApiError(RuntimeError):
    pass


class OddsApiClient:
    def __init__(self, api_key: str, session: requests.Session | None = None, base_url: str = API_URL):
        if not api_key:
            raise OddsApiError("Clé The Odds API manquante.")
        self.api_key = api_key
        self.session = session or requests.Session()
        self.base_url = base_url
        self.requests_remaining: str | None = None
        self.requests_used: str | None = None

    def _get(self, path: str, **params: Any) -> Any:
        resp = self.session.get(f"{self.base_url}{path}", params={"apiKey": self.api_key, **params}, timeout=20)
        self.requests_remaining = resp.headers.get("x-requests-remaining", self.requests_remaining)
        self.requests_used = resp.headers.get("x-requests-used", self.requests_used)
        if resp.status_code == 401:
            raise OddsApiError("Clé refusée par The Odds API : vérifiez-la sur votre compte.")
        if resp.status_code == 429:
            raise OddsApiError("Quota de requêtes atteint pour ce mois (ou trop d'appels rapprochés).")
        if resp.status_code >= 400:
            raise OddsApiError(f"Erreur The Odds API ({resp.status_code}) : {resp.text[:200]}")
        return resp.json()

    def tennis_tournaments(self, tour: str | None = None) -> list[dict]:
        """Tournois de tennis en cours ou à venir proposés par l'API (appel gratuit).

        ``tour`` : "atp", "wta", ou None pour les deux circuits.
        """
        sports = self._get("/sports")
        out = [s for s in sports if s.get("group") == "Tennis" and s.get("active")]
        if tour:
            out = [s for s in out if s["key"].startswith(f"tennis_{tour}")]
        return out

    def odds(self, sport_key: str, regions: str = "eu") -> list[dict]:
        return self._get(f"/sports/{sport_key}/odds", regions=regions, markets="h2h", oddsFormat="decimal")

    def upcoming_matches(self, tour: str | None = None, regions: str = "eu") -> list[UpcomingMatch]:
        matches: list[UpcomingMatch] = []
        for sport in self.tennis_tournaments(tour):
            matches.extend(parse_events(self.odds(sport["key"], regions)))
        return sorted(matches, key=lambda m: m.start)


def parse_events(events: list[dict]) -> list[UpcomingMatch]:
    matches = []
    for ev in events:
        a, b = ev.get("home_team"), ev.get("away_team")
        if not a or not b:
            continue
        m = UpcomingMatch(
            id=ev["id"],
            tournament=ev.get("sport_title", ""),
            sport_key=ev.get("sport_key", ""),
            start=datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(timezone.utc),
            player_a=a,
            player_b=b,
        )
        for book in ev.get("bookmakers", []):
            h2h = next((mk for mk in book.get("markets", []) if mk.get("key") == "h2h"), None)
            if not h2h:
                continue
            prices = {o["name"]: o["price"] for o in h2h.get("outcomes", [])}
            if a in prices and b in prices and prices[a] > 1 and prices[b] > 1:
                m.books[book["key"]] = BookOdds(book["key"], book.get("title", book["key"]), prices[a], prices[b])
        matches.append(m)
    return matches


def guess_surface(tournament: str) -> str:
    name = _fold(tournament)
    if any(w in name for w in GRASS_WORDS):
        return "Grass"
    if any(w in name for w in CLAY_WORDS):
        return "Clay"
    return "Hard"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower().replace(".", " ")).strip()


def match_player(full_name: str, known: list[str]) -> str | None:
    """Retrouve « Jannik Sinner » sous la forme tennis-data « Sinner J. ».

    Les noms composés sont essayés de la plus longue à la plus courte
    combinaison (« Alex de Minaur » → « De Minaur A. »).
    """
    index: dict[str, str] = {}
    for k in known:
        index.setdefault(_fold(k), k)
    parts = full_name.split()
    for i in range(1, len(parts)):
        first, last = parts[:i], parts[i:]
        initials = " ".join(p[0] for p in first)
        for candidate in (f"{' '.join(last)} {initials}", f"{' '.join(last)} {first[0][0]}"):
            hit = index.get(_fold(candidate))
            if hit:
                return hit
    return None
