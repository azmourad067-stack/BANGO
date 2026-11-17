"""Journal des opportunités : garde une trace de chaque cote à valeur repérée.

Chaque relevé ajoute les issues dont la valeur est positive. Une même issue
(même match, même pari, même bookmaker) n'est enregistrée qu'une fois : on met
à jour sa dernière observation et sa meilleure valeur. Le journal permet de
mesurer, sur plusieurs semaines, combien de paris à valeur chaque sport offre
réellement chez les bookmakers français.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .schedule import UpcomingMatch

COLUMNS = [
    "first_seen", "last_seen", "sport", "competition", "event_id", "match", "start",
    "pick", "bookmaker", "odds", "fair_odds", "edge", "best_edge", "seen",
]


def opportunities(matches: list[UpcomingMatch], book_keys: list[str], now: datetime) -> pd.DataFrame:
    """Toutes les issues à valeur positive (seuil 0 %) au moment du relevé."""
    rows = []
    for m in matches:
        res = m.assess(book_keys, min_edge=0.0)
        if res is None:
            continue
        for side in res.sides:
            if 0 < side.edge <= 0.20:  # au-delà de 20 %, c'est presque toujours une erreur de cote
                rows.append(
                    {
                        "first_seen": now, "last_seen": now, "sport": m.sport, "competition": m.tournament,
                        "event_id": m.id, "match": m.label, "start": m.start, "pick": side.label,
                        "bookmaker": side.bookmaker, "odds": side.offered_odds, "fair_odds": round(side.fair_odds, 3),
                        "edge": round(side.edge, 4), "best_edge": round(side.edge, 4), "seen": 1,
                    }
                )
    return pd.DataFrame(rows, columns=COLUMNS)


def load(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    for col in ("first_seen", "last_seen", "start"):
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601")
    return df


def record(
    matches: list[UpcomingMatch],
    book_keys: list[str],
    path: str | Path,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, int]:
    """Ajoute le relevé au journal. Renvoie le journal à jour et le nombre de nouvelles opportunités."""
    now = now or datetime.now(timezone.utc)
    fresh = opportunities(matches, book_keys, now)
    journal = load(path)
    key = ["event_id", "pick", "bookmaker"]

    new_count = 0
    if not fresh.empty:
        if journal.empty:
            merged = fresh
            new_count = len(fresh)
        else:
            known = journal.set_index(key)
            fresh_idx = fresh.set_index(key)
            seen_again = fresh_idx.index.intersection(known.index)
            # Déjà connues : dernière observation, cote actuelle et meilleure valeur.
            known.loc[seen_again, "last_seen"] = now
            known.loc[seen_again, "odds"] = fresh_idx.loc[seen_again, "odds"]
            known.loc[seen_again, "edge"] = fresh_idx.loc[seen_again, "edge"]
            known.loc[seen_again, "best_edge"] = known.loc[seen_again, "best_edge"].combine(
                fresh_idx.loc[seen_again, "edge"], max
            )
            known.loc[seen_again, "seen"] = known.loc[seen_again, "seen"] + 1
            brand_new = fresh_idx.loc[fresh_idx.index.difference(known.index)]
            new_count = len(brand_new)
            merged = pd.concat([known, brand_new]).reset_index()[COLUMNS]
        journal = merged.sort_values(["first_seen", "start"]).reset_index(drop=True)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    journal.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    return journal, new_count


def daily_counts(journal: pd.DataFrame, min_edge: float = 0.02) -> pd.DataFrame:
    """Nombre de paris à valeur repérés par jour (date de première observation) et par sport."""
    if journal.empty:
        return pd.DataFrame()
    j = journal[journal["best_edge"] >= min_edge].copy()
    if j.empty:
        return pd.DataFrame()
    # Un seul pari par match et par jour : on ne joue pas deux issues du même match.
    j["day"] = j["first_seen"].dt.tz_convert("Europe/Paris").dt.date
    j = j.sort_values("best_edge", ascending=False).drop_duplicates(["day", "event_id"])
    table = j.pivot_table(index="day", columns="sport", values="event_id", aggfunc="count", fill_value=0)
    table["total"] = table.sum(axis=1)
    return table.sort_index()
