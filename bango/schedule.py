"""Programme des matchs à venir et cotes en direct via The Odds API (https://the-odds-api.com).

Sports couverts : tennis (ATP, WTA), football et basket. Une clé gratuite
(environ 500 requêtes par mois) suffit pour un usage léger.

Coût : on demande Pinnacle et les opérateurs français par leur nom
(paramètre ``bookmakers``, moins de 10 bookmakers), ce qui coûte 1 requête
par compétition à chaque actualisation. La liste des compétitions est gratuite.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .value import ValueAssessment, assess_market

API_URL = "https://api.the-odds-api.com/v4"
REFERENCE_BOOK = "pinnacle"
FRENCH_BOOKS = ("winamax_fr", "betclic_fr", "unibet_fr", "parionssport_fr", "pmu_fr", "netbet_fr")
REQUEST_BOOKS = (REFERENCE_BOOK, *FRENCH_BOOKS)
DRAW = "Draw"

SPORTS = {"tennis": "Tennis", "football": "Football", "basket": "Basket"}
_API_GROUPS = {"Tennis": "tennis", "Soccer": "football", "Basketball": "basket"}

# Compétitions suivies par défaut (le tennis prend automatiquement les tournois en cours).
DEFAULT_LEAGUES = (
    "soccer_france_ligue_one",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_uefa_champs_league",
    "basketball_nba",
    "basketball_euroleague",
)

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
    prices: dict[str, float]

    # Accès pratiques pour un marché à deux issues.
    def price(self, outcome: str) -> float | None:
        return self.prices.get(outcome)


@dataclass
class UpcomingMatch:
    id: str
    tournament: str
    sport_key: str
    start: datetime
    player_a: str  # équipe à domicile au football et au basket
    player_b: str
    outcomes: list[str] = field(default_factory=list)
    books: dict[str, BookOdds] = field(default_factory=dict)

    @property
    def sport(self) -> str:
        if self.sport_key.startswith("tennis"):
            return "tennis"
        if self.sport_key.startswith("soccer"):
            return "football"
        if self.sport_key.startswith("basketball"):
            return "basket"
        return "autre"

    @property
    def tour(self) -> str:
        return "wta" if self.sport_key.startswith("tennis_wta") else "atp"

    @property
    def surface(self) -> str:
        return guess_surface(self.tournament)

    @property
    def label(self) -> str:
        return f"{self.player_a} – {self.player_b}"

    @property
    def reference(self) -> BookOdds | None:
        return self.books.get(REFERENCE_BOOK)

    def best_odds(self, book_keys: list[str]) -> dict[str, BookOdds]:
        """Pour chaque issue, le bookmaker qui la paie le mieux parmi ceux choisis."""
        best: dict[str, BookOdds] = {}
        for key in book_keys:
            book = self.books.get(key)
            if not book:
                continue
            for outcome in self.outcomes:
                price = book.price(outcome)
                if price and (outcome not in best or price > best[outcome].price(outcome)):
                    best[outcome] = book
        return best

    def outcome_label(self, outcome: str) -> str:
        return "Match nul" if outcome == DRAW else outcome

    def assess(self, book_keys: list[str], min_edge: float = 0.02, bankroll: float = 1000.0) -> ValueAssessment | None:
        ref = self.reference
        best = self.best_odds(book_keys)
        if ref is None or any(o not in best or ref.price(o) is None for o in self.outcomes):
            return None
        return assess_market(
            [ref.price(o) for o in self.outcomes],
            [best[o].price(o) for o in self.outcomes],
            [self.outcome_label(o) for o in self.outcomes],
            bookmakers=[best[o].title for o in self.outcomes],
            min_edge=min_edge,
            bankroll=bankroll,
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
        self.raw_events: list[dict] = []  # réponses brutes, pour les enregistrer telles quelles

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

    def competitions(self) -> list[dict]:
        """Compétitions actives de tennis, football et basket (appel gratuit).

        Chaque entrée reçoit un champ ``sport`` : "tennis", "football" ou "basket".
        """
        out = []
        for s in self._get("/sports"):
            sport = _API_GROUPS.get(s.get("group", ""))
            if sport and s.get("active") and not s.get("has_outrights"):
                out.append({**s, "sport": sport})
        return out

    def tennis_tournaments(self, tour: str | None = None) -> list[dict]:
        """Tournois de tennis en cours. ``tour`` : "atp", "wta", ou None pour les deux."""
        out = [c for c in self.competitions() if c["sport"] == "tennis"]
        if tour:
            out = [c for c in out if c["key"].startswith(f"tennis_{tour}")]
        return out

    def odds(self, sport_key: str) -> list[dict]:
        return self._get(
            f"/sports/{sport_key}/odds",
            bookmakers=",".join(REQUEST_BOOKS),
            markets="h2h",
            oddsFormat="decimal",
        )

    def upcoming(self, sport_keys: list[str]) -> list[UpcomingMatch]:
        matches: list[UpcomingMatch] = []
        for key in sport_keys:
            events = self.odds(key)
            self.raw_events.extend(events)
            matches.extend(parse_events(events))
        return sorted(matches, key=lambda m: m.start)

    def upcoming_matches(self, tour: str | None = None, regions: str | None = None) -> list[UpcomingMatch]:
        """Matchs de tennis à venir (ATP, WTA ou les deux)."""
        return self.upcoming([t["key"] for t in self.tennis_tournaments(tour)])


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
            outcomes=[a, b],
        )
        for book in ev.get("bookmakers", []):
            h2h = next((mk for mk in book.get("markets", []) if mk.get("key") == "h2h"), None)
            if not h2h:
                continue
            prices = {o["name"]: o["price"] for o in h2h.get("outcomes", []) if o.get("price", 0) > 1}
            if DRAW in prices and DRAW not in m.outcomes:
                m.outcomes = [a, DRAW, b]
            m.books[book["key"]] = BookOdds(book["key"], book.get("title", book["key"]), prices)
        # Un bookmaker qui ne cote pas toutes les issues ne peut pas servir.
        m.books = {k: bk for k, bk in m.books.items() if all(o in bk.prices for o in m.outcomes)}
        matches.append(m)
    return matches


def save_snapshot(path: str | Path, events: list[dict], scanned_at: datetime, remaining: str | None = None) -> None:
    """Enregistre un relevé complet pour l'afficher plus tard sans consommer de requête."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanned_at": scanned_at.astimezone(timezone.utc).isoformat(),
        "requests_remaining": remaining,
        "events": events,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def load_snapshot(path: str | Path) -> tuple[list[UpcomingMatch], datetime, str | None] | None:
    """Relit le dernier relevé enregistré, ou None s'il n'y en a pas."""
    path = Path(path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    scanned_at = datetime.fromisoformat(payload["scanned_at"])
    matches = sorted(parse_events(payload.get("events", [])), key=lambda m: m.start)
    return matches, scanned_at, payload.get("requests_remaining")


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
