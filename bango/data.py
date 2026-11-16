"""Chargement des fichiers de résultats et de cotes au format tennis-data.co.uk.

Le site publie un fichier par saison (ATP et WTA, .xlsx ou .csv) avec, pour
chaque match : vainqueur, perdant, surface, tour, et les cotes de plusieurs
bookmakers (Bet365, Pinnacle, moyenne et maximum du marché).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

# Préfixes de colonnes de cotes : <préfixe>W pour le vainqueur, <préfixe>L pour le perdant.
BOOKMAKERS = {
    "B365": "Bet365",
    "PS": "Pinnacle",
    "Max": "Meilleure cote du marché",
    "Avg": "Cote moyenne du marché",
}

ROUND_ORDER = {
    "0th Round": 0,
    "1st Round": 1,
    "2nd Round": 2,
    "3rd Round": 3,
    "4th Round": 4,
    "Round Robin": 4,
    "Quarterfinals": 5,
    "Semifinals": 6,
    "The Final": 7,
}

REQUIRED = ["Date", "Winner", "Loser", "Surface"]


def _read_one(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path, encoding="latin-1")


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Met un tableau brut tennis-data au format attendu par le moteur."""
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {', '.join(missing)}")

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce"),
            "tournament": raw.get("Tournament", pd.Series("", index=raw.index)).astype(str),
            "series": raw.get("Series", raw.get("Tier", pd.Series("", index=raw.index))).astype(str),
            "surface": raw["Surface"].astype(str).str.strip(),
            "round": raw.get("Round", pd.Series("", index=raw.index)).astype(str),
            "best_of": pd.to_numeric(raw.get("Best of", pd.Series(3, index=raw.index)), errors="coerce")
            .fillna(3)
            .astype(int),
            "winner": raw["Winner"].astype(str).str.strip(),
            "loser": raw["Loser"].astype(str).str.strip(),
            "wrank": pd.to_numeric(raw.get("WRank"), errors="coerce") if "WRank" in raw else pd.NA,
            "lrank": pd.to_numeric(raw.get("LRank"), errors="coerce") if "LRank" in raw else pd.NA,
            "comment": raw.get("Comment", pd.Series("Completed", index=raw.index)).astype(str).str.strip(),
        }
    )
    for prefix in BOOKMAKERS:
        for side, col in (("w", f"{prefix}W"), ("l", f"{prefix}L")):
            df[f"{prefix.lower()}_{side}"] = pd.to_numeric(raw[col], errors="coerce") if col in raw else float("nan")

    df = df.dropna(subset=["date"])
    df["completed"] = df["comment"].str.lower().eq("completed")
    df["round_order"] = df["round"].map(ROUND_ORDER).fillna(1).astype(int)
    df = df.sort_values(["date", "round_order"], kind="stable").reset_index(drop=True)
    return df


def load_matches(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Charge et fusionne plusieurs saisons, triées chronologiquement."""
    files = [Path(p) for p in paths]
    if not files:
        raise ValueError("Aucun fichier de données fourni.")
    frames = [normalize(_read_one(p)) for p in files]
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["date", "round_order"], kind="stable").reset_index(drop=True)
