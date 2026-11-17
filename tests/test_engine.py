import math

import pandas as pd
import pytest

from bango.backtest import run_backtest
from bango.cli import main
from bango.data import normalize
from bango.elo import SurfaceElo, bo3_to_bo5, win_probability
from bango.odds import expected_value, fair_probabilities, kelly_fraction, overround
from bango.strategy import StrategyConfig, combine, stake_for
from bango.synthetic import generate


# --- Cotes -----------------------------------------------------------------


def test_overround_and_fair_probabilities_sum_to_one():
    assert overround(1.90, 1.90) == pytest.approx(2 / 1.9 - 1)
    for method in ("proportional", "power"):
        a, b = fair_probabilities(1.50, 2.60, method)
        assert a + b == pytest.approx(1.0)
        assert a > b


def test_power_devig_gives_favourite_more_than_proportional():
    prop, _ = fair_probabilities(1.25, 4.00, "proportional")
    power, _ = fair_probabilities(1.25, 4.00, "power")
    assert power > prop


def test_expected_value_and_kelly():
    assert expected_value(0.55, 2.0) == pytest.approx(0.10)
    assert kelly_fraction(0.55, 2.0) == pytest.approx(0.10)
    assert kelly_fraction(0.40, 2.0) == 0.0


# --- Elo -------------------------------------------------------------------


def test_win_probability_is_symmetric():
    assert win_probability(1600, 1500) + win_probability(1500, 1600) == pytest.approx(1.0)
    assert win_probability(1500, 1500) == pytest.approx(0.5)


def test_bo5_favours_the_favourite_more():
    assert bo3_to_bo5(0.5) == pytest.approx(0.5, abs=1e-6)
    assert bo3_to_bo5(0.70) > 0.70
    assert bo3_to_bo5(0.30) < 0.30


def test_elo_learns_who_is_stronger_and_by_surface():
    elo = SurfaceElo()
    for _ in range(30):
        elo.update("Fort A.", "Faible B.", "Clay")
        elo.update("Faible B.", "Fort A.", "Grass")
        elo.update("Fort A.", "Faible B.", "Clay")
    assert elo.predict("Fort A.", "Faible B.", "Clay") > 0.5
    assert elo.predict("Fort A.", "Faible B.", "Clay") > elo.predict("Fort A.", "Faible B.", "Grass")
    assert elo.matches_played("Fort A.") == 90


# --- Données ---------------------------------------------------------------


def _raw(rows):
    return pd.DataFrame(rows)


def test_normalize_reads_tennis_data_columns():
    raw = _raw(
        [
            {"Date": "02/01/2024", "Surface": "Hard", "Round": "The Final", "Winner": "A", "Loser": "B",
             "Comment": "Completed", "B365W": 1.5, "B365L": 2.6, "PSW": 1.55, "PSL": 2.7, "Best of": 3},
            {"Date": "02/01/2024", "Surface": "Hard", "Round": "1st Round", "Winner": "C", "Loser": "D",
             "Comment": "Retired", "B365W": 1.8, "B365L": 2.0, "PSW": 1.85, "PSL": 2.05, "Best of": 3},
        ]
    )
    df = normalize(raw)
    assert list(df["winner"]) == ["C", "A"]  # trié par tour dans la même journée
    assert list(df["completed"]) == [False, True]
    assert df.loc[1, "ps_w"] == 1.55
    assert math.isnan(df.loc[0, "max_w"])


def test_normalize_rejects_missing_columns():
    with pytest.raises(ValueError):
        normalize(_raw([{"Date": "01/01/2024", "Winner": "A"}]))


# --- Stratégie -------------------------------------------------------------


def test_combine_and_stake():
    cfg = StrategyConfig(model="blend", blend_weight=0.5)
    assert combine(0.6, 0.6, cfg) == pytest.approx(0.6)
    assert combine(None, 0.6, cfg) is None
    assert stake_for(0.6, 2.0, 1000, StrategyConfig(staking="flat", flat_stake=50)) == 20  # plafond 2 %
    kelly = stake_for(0.55, 2.0, 1000, StrategyConfig(staking="kelly"))
    assert kelly == pytest.approx(20.0)  # Kelly 10 % × 0.25 = 2.5 %, plafonné à 2 %
    with pytest.raises(ValueError):
        StrategyConfig(model="magie")


# --- Backtest --------------------------------------------------------------


def test_backtest_has_no_lookahead():
    """La proba utilisée pour un match ne doit pas dépendre de son résultat."""
    matches = normalize(generate(n_players=40, n_matches=3000, seed=1))
    flipped = matches.copy()
    last = flipped.index[-1]
    w, l = flipped.at[last, "winner"], flipped.at[last, "loser"]
    flipped.at[last, "winner"], flipped.at[last, "loser"] = l, w
    for side in ("b365", "ps", "max", "avg"):
        flipped.at[last, f"{side}_w"], flipped.at[last, f"{side}_l"] = matches.at[last, f"{side}_l"], matches.at[last, f"{side}_w"]

    cfg = StrategyConfig(model="elo", min_matches=5)
    a = run_backtest(matches, cfg).bets
    b = run_backtest(flipped, cfg).bets
    assert len(a) == len(b)
    if len(a) and a.iloc[-1]["date"] == matches.at[last, "date"]:
        # Même pari choisi (même joueur, même cote), seul le résultat change.
        assert a.iloc[-1]["player"] in (w, l)
        assert a.iloc[-1]["odds"] == pytest.approx(b.iloc[-1]["odds"])


def test_backtest_summary_is_consistent():
    matches = normalize(generate(n_players=60, n_matches=5000, seed=3))
    res = run_backtest(matches, StrategyConfig(model="market"), initial_bankroll=1000)
    s = res.summary
    assert s["paris"] == len(res.bets) > 0
    assert s["gain_net"] == pytest.approx(res.bets["pnl"].sum(), abs=0.01)
    assert s["bankroll_finale"] == pytest.approx(1000 + res.bets["pnl"].sum(), abs=0.01)
    assert (res.bets["edge"] >= 0.03).all() and (res.bets["edge"] <= 0.20).all()
    assert res.bets["odds"].between(1.30, 4.00).all()
    assert res.by_year["paris"].sum() == s["paris"]
    assert 0 <= s["drawdown_max"] < 1


def test_haircut_lowers_returns():
    matches = normalize(generate(n_players=60, n_matches=5000, seed=3))
    base = run_backtest(matches, StrategyConfig(model="market"))
    cut = run_backtest(matches, StrategyConfig(model="market", price_haircut=0.95))
    assert cut.summary["paris"] < base.summary["paris"]


# --- Ligne de commande -----------------------------------------------------


def test_cli_backtest_and_predict(tmp_path, capsys):
    path = tmp_path / "saison.csv"
    generate(n_players=30, n_matches=2500, seed=5).to_csv(path, index=False)

    assert main(["backtest", str(path), "--model", "blend", "--bet-from", "2019-04-01", "--export", str(tmp_path / "paris.csv")]) == 0
    out = capsys.readouterr().out
    assert "ROI" in out

    assert main(["predict", str(path), "--a", "Joueur000 X.", "--b", "Joueur001 X.", "--odds-a", "1.8", "--odds-b", "2.1"]) == 0
    assert "Probabilité Elo" in capsys.readouterr().out

    assert main(["predict", str(path), "--a", "Inconnu Z.", "--b", "Joueur001 X."]) == 1
    assert main(["ranking", str(path), "--top", "5"]) == 0


def test_cli_value(capsys):
    assert main(["value", "--ref", "1.80", "2.10", "--odds", "1.95", "1.90"]) == 0
    out = capsys.readouterr().out
    assert "Pari à valeur : joueur A à 1.95" in out
    assert main(["value", "--ref", "1.80", "2.10", "--odds", "1.75", "2.05"]) == 0
    assert "Pas de pari" in capsys.readouterr().out


def test_normalize_detects_wta_files_and_cli_filters_tour(tmp_path, capsys):
    atp = generate(n_players=30, n_matches=2500, seed=5)
    wta = generate(n_players=30, n_matches=2500, seed=6).rename(columns={"Best of": "Tier"})
    wta.insert(0, "WTA", 1)
    wta["Winner"] = "F-" + wta["Winner"]
    wta["Loser"] = "F-" + wta["Loser"]
    assert set(normalize(wta)["tour"]) == {"wta"}
    assert set(normalize(atp)["tour"]) == {"atp"}
    assert normalize(wta)["best_of"].eq(3).all()

    pa, pw = tmp_path / "atp.csv", tmp_path / "wta.csv"
    atp.to_csv(pa, index=False)
    wta.to_csv(pw, index=False)
    assert main(["backtest", str(pa), str(pw), "--tour", "wta", "--bet-from", "2019-04-01"]) == 0
    assert "2500 matchs chargés" in capsys.readouterr().out
    assert main(["backtest", str(pa), "--tour", "wta"]) == 1
