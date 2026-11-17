"""Règles de sélection et de mise d'un pari."""

from __future__ import annotations

from dataclasses import dataclass

from .odds import kelly_fraction, logit, sigmoid

MODELS = ("elo", "market", "blend")


@dataclass
class StrategyConfig:
    # Origine de la probabilité :
    #   elo    : uniquement notre modèle Elo
    #   market : la cote Pinnacle sans marge (bookmaker de référence, le plus juste)
    #   blend  : mélange des deux (en logit), pondéré par blend_weight
    model: str = "elo"
    blend_weight: float = 0.3  # part de l'Elo dans le mélange
    devig_method: str = "power"

    # Cote à laquelle on parie. "b365" approche un bookmaker grand public.
    price_source: str = "b365"
    # Multiplicateur appliqué à la cote pour simuler un opérateur moins généreux
    # (ex. 0.97 pour un opérateur français agréé ANJ, plus margé).
    price_haircut: float = 1.0

    min_edge: float = 0.03  # valeur attendue minimale (3 %)
    # Au-delà, l'écart vient presque toujours d'une erreur du modèle
    # (blessure, forme, info manquante) plutôt que d'une vraie aubaine.
    max_edge: float = 0.20
    min_odds: float = 1.30
    max_odds: float = 4.00
    min_matches: int = 30  # historique minimal de chaque joueur pour l'Elo

    staking: str = "flat"  # "flat" ou "kelly"
    flat_stake: float = 10.0
    kelly_multiplier: float = 0.25  # Kelly fractionné : bien plus sûr que Kelly complet
    max_stake_pct: float = 0.02  # jamais plus de 2 % de la bankroll sur un pari

    def __post_init__(self) -> None:
        if self.model not in MODELS:
            raise ValueError(f"Modèle inconnu : {self.model} (choix : {', '.join(MODELS)})")
        if self.staking not in ("flat", "kelly"):
            raise ValueError(f"Mode de mise inconnu : {self.staking}")


def combine(elo_p: float | None, market_p: float | None, cfg: StrategyConfig) -> float | None:
    """Probabilité retenue pour le pari selon le modèle choisi."""
    if cfg.model == "elo":
        return elo_p
    if cfg.model == "market":
        return market_p
    if elo_p is None or market_p is None:
        return None
    w = cfg.blend_weight
    return sigmoid(w * logit(elo_p) + (1 - w) * logit(market_p))


def stake_for(probability: float, odds: float, bankroll: float, cfg: StrategyConfig) -> float:
    cap = bankroll * cfg.max_stake_pct
    if cfg.staking == "flat":
        return min(cfg.flat_stake, cap) if bankroll > 0 else 0.0
    f = kelly_fraction(probability, odds) * cfg.kelly_multiplier
    return round(min(f * bankroll, cap), 2)
