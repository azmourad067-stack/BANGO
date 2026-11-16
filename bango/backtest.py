"""Backtest chronologique : on prédit chaque match avec l'information disponible
avant ce match uniquement, on parie si la stratégie le dit, puis on met à jour
les notes Elo avec le résultat."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .elo import EloConfig, SurfaceElo
from .odds import expected_value, fair_probabilities
from .strategy import StrategyConfig, combine, stake_for


@dataclass
class BacktestResult:
    bets: pd.DataFrame
    summary: dict
    by_year: pd.DataFrame
    by_surface: pd.DataFrame
    calibration: dict
    elo: SurfaceElo = field(repr=False)


def _valid(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and x > 1.0


def run_backtest(
    matches: pd.DataFrame,
    strategy: StrategyConfig | None = None,
    elo_config: EloConfig | None = None,
    bet_from: str | pd.Timestamp | None = None,
    initial_bankroll: float = 1000.0,
) -> BacktestResult:
    cfg = strategy or StrategyConfig()
    elo = SurfaceElo(elo_config)

    if bet_from is None:
        # Par défaut, la première année sert seulement à construire les notes.
        bet_from = matches["date"].min() + pd.Timedelta(days=365)
    bet_from = pd.Timestamp(bet_from)

    price_w, price_l = f"{cfg.price_source}_w", f"{cfg.price_source}_l"
    for col in (price_w, price_l):
        if col not in matches.columns:
            raise ValueError(f"Source de cotes inconnue : {cfg.price_source}")

    bankroll = initial_bankroll
    peak = bankroll
    max_drawdown = 0.0
    bets: list[dict] = []
    calib_rows: list[tuple[float, float]] = []  # (proba Elo du vainqueur, proba Pinnacle du vainqueur)

    for row in matches.itertuples(index=False):
        if not row.completed:
            # Abandons et forfaits : règles de règlement variables selon les bookmakers,
            # on ne parie pas et on ne met pas les notes à jour.
            continue

        surface, best_of = row.surface, int(row.best_of)
        elo_ready = (
            elo.matches_played(row.winner) >= cfg.min_matches and elo.matches_played(row.loser) >= cfg.min_matches
        )
        elo_w = elo.predict(row.winner, row.loser, surface, best_of, row.wrank, row.lrank) if elo_ready else None

        market_w = None
        if _valid(row.ps_w) and _valid(row.ps_l):
            market_w, _ = fair_probabilities(row.ps_w, row.ps_l, cfg.devig_method)

        if row.date >= bet_from:
            if elo_w is not None and market_w is not None:
                calib_rows.append((elo_w, market_w))

            p_w = combine(elo_w, market_w, cfg)
            odds_w, odds_l = getattr(row, price_w), getattr(row, price_l)
            if p_w is not None and _valid(odds_w) and _valid(odds_l):
                candidates = []
                for side, p, odds, fair in (
                    ("winner", p_w, odds_w, market_w),
                    ("loser", 1 - p_w, odds_l, None if market_w is None else 1 - market_w),
                ):
                    price = max(1.01, odds * cfg.price_haircut)
                    ev = expected_value(p, price)
                    if cfg.min_edge <= ev <= cfg.max_edge and cfg.min_odds <= price <= cfg.max_odds:
                        candidates.append((ev, side, p, price, fair))

                if candidates:
                    ev, side, p, price, fair = max(candidates)
                    stake = stake_for(p, price, bankroll, cfg)
                    if stake > 0:
                        won = side == "winner"
                        pnl = stake * (price - 1) if won else -stake
                        bankroll += pnl
                        peak = max(peak, bankroll)
                        max_drawdown = max(max_drawdown, (peak - bankroll) / peak)
                        player = row.winner if won else row.loser
                        opponent = row.loser if won else row.winner
                        bets.append(
                            {
                                "date": row.date,
                                "tournament": row.tournament,
                                "surface": surface,
                                "round": row.round,
                                "player": player,
                                "opponent": opponent,
                                "probability": p,
                                "odds": price,
                                "edge": ev,
                                "stake": stake,
                                "won": won,
                                "pnl": pnl,
                                "bankroll": bankroll,
                                # CLV : valeur de notre cote face au prix juste Pinnacle de clôture
                                "clv": None if fair is None else price * fair - 1,
                            }
                        )

        elo.update(row.winner, row.loser, surface, row.wrank, row.lrank)

    bets_df = pd.DataFrame(bets)
    return BacktestResult(
        bets=bets_df,
        summary=_summary(bets_df, initial_bankroll, bankroll, max_drawdown),
        by_year=_breakdown(bets_df, bets_df["date"].dt.year if len(bets_df) else None),
        by_surface=_breakdown(bets_df, "surface"),
        calibration=_calibration(calib_rows),
        elo=elo,
    )


def _summary(bets: pd.DataFrame, initial: float, final: float, max_dd: float) -> dict:
    if bets.empty:
        return {"paris": 0, "bankroll_initiale": initial, "bankroll_finale": final}
    staked = bets["stake"].sum()
    profit = bets["pnl"].sum()
    returns = bets["pnl"] / bets["stake"]  # rendement par euro misé
    n = len(bets)
    t_stat = returns.mean() / (returns.std(ddof=1) / math.sqrt(n)) if n > 1 and returns.std(ddof=1) > 0 else 0.0
    clv = bets["clv"].dropna()
    return {
        "paris": n,
        "mise_totale": round(staked, 2),
        "gain_net": round(profit, 2),
        "roi": profit / staked,
        "taux_reussite": bets["won"].mean(),
        "cote_moyenne": bets["odds"].mean(),
        "valeur_attendue_moyenne": bets["edge"].mean(),
        "clv_moyen": clv.mean() if len(clv) else float("nan"),
        "part_clv_positif": (clv > 0).mean() if len(clv) else float("nan"),
        "drawdown_max": max_dd,
        "bankroll_initiale": initial,
        "bankroll_finale": round(final, 2),
        # t > 2 : résultat difficilement attribuable à la chance seule
        "t_stat": t_stat,
    }


def _breakdown(bets: pd.DataFrame, key) -> pd.DataFrame:
    if bets.empty:
        return pd.DataFrame()
    g = bets.groupby(key)
    out = pd.DataFrame(
        {
            "paris": g.size(),
            "mise": g["stake"].sum().round(2),
            "gain_net": g["pnl"].sum().round(2),
            "taux_reussite": g["won"].mean().round(3),
            "clv_moyen": g["clv"].mean().round(4),
        }
    )
    out["roi"] = (out["gain_net"] / out["mise"]).round(4)
    return out


def _calibration(rows: list[tuple[float, float]]) -> dict:
    """Compare la précision de l'Elo et de Pinnacle sur les mêmes matchs.

    Le vainqueur est connu, donc la perte logarithmique est -log(p_vainqueur).
    Plus c'est bas, meilleur est le modèle. Battre Pinnacle sur ce critère est
    très difficile : c'est la référence du marché.
    """
    if not rows:
        return {}
    arr = np.array(rows)
    eps = 1e-12
    return {
        "matchs": len(arr),
        "log_loss_elo": float(-np.log(arr[:, 0] + eps).mean()),
        "log_loss_pinnacle": float(-np.log(arr[:, 1] + eps).mean()),
        "brier_elo": float(((1 - arr[:, 0]) ** 2).mean()),
        "brier_pinnacle": float(((1 - arr[:, 1]) ** 2).mean()),
        "favori_elo_gagne": float((arr[:, 0] > 0.5).mean()),
        "favori_pinnacle_gagne": float((arr[:, 1] > 0.5).mean()),
    }
