"""Interface web de BANGO. Lancement local : ``streamlit run streamlit_app.py``."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from bango.backtest import run_backtest
from bango.data import normalize
from bango.elo import SurfaceElo
from bango.strategy import StrategyConfig
from bango.value import assess_value

st.set_page_config(page_title="BANGO · Value betting tennis", page_icon="🎾", layout="wide")

MODEL_LABELS = {
    "market": "Pinnacle comme référence (recommandé)",
    "elo": "Elo seul",
    "blend": "Mélange Elo + Pinnacle",
}
PRICE_LABELS = {
    "b365": "Bet365",
    "avg": "Cote moyenne du marché",
    "max": "Meilleure cote du marché",
}
SURFACES = ["Hard", "Clay", "Grass"]
SURFACE_LABELS = {"Hard": "Dur", "Clay": "Terre battue", "Grass": "Gazon"}


@st.cache_data(show_spinner="Lecture des fichiers…")
def load_files(files: tuple[tuple[str, bytes], ...]) -> pd.DataFrame:
    frames = []
    for name, content in files:
        buf = io.BytesIO(content)
        raw = pd.read_excel(buf) if name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(buf, encoding="latin-1")
        frames.append(normalize(raw))
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["date", "round_order"], kind="stable").reset_index(drop=True)


@st.cache_resource(show_spinner="Calcul des notes Elo…")
def build_elo(_matches: pd.DataFrame, key: str) -> SurfaceElo:
    elo = SurfaceElo()
    for row in _matches.itertuples(index=False):
        if row.completed:
            elo.update(row.winner, row.loser, row.surface, row.wrank, row.lrank)
    return elo


def pct(x: float, signed: bool = True) -> str:
    return f"{x * 100:+.1f} %" if signed else f"{x * 100:.1f} %"


# --- Barre latérale : données historiques ---------------------------------

with st.sidebar:
    st.header("Données historiques")
    st.caption(
        "Fichiers de saison ATP au format tennis-data.co.uk (.xlsx). "
        "Nécessaires pour le backtest et le classement Elo, pas pour l'analyse d'un match."
    )
    uploads = st.file_uploader("Saisons", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    matches = None
    if uploads:
        try:
            matches = load_files(tuple((f.name, f.getvalue()) for f in uploads))
            count = f"{len(matches):,}".replace(",", " ")
            st.success(f"{count} matchs, du {matches['date'].min():%d/%m/%Y} au {matches['date'].max():%d/%m/%Y}")
        except ValueError as exc:
            st.error(f"Fichier illisible : {exc}")
    st.divider()
    st.caption(
        "Les paris comportent des risques : endettement, dépendance. "
        "Joueurs Info Service : 09 74 75 13 13 (appel non surtaxé)."
    )

st.title("BANGO")
st.caption("Value betting tennis : ne parier que lorsque la cote paie plus que le risque réel.")

tab_value, tab_backtest, tab_elo = st.tabs(["Analyser un match", "Backtest", "Classement Elo"])

# --- Onglet 1 : analyse d'un match ------------------------------------------

with tab_value:
    st.markdown(
        "Relevez la cote **Pinnacle** sur un comparateur de cotes, puis la cote de **votre bookmaker**. "
        "BANGO retire la marge de Pinnacle pour obtenir le prix juste et vous dit si votre cote a de la valeur."
    )
    c1, c2 = st.columns(2)
    with c1:
        name_a = st.text_input("Joueur A", "Joueur A")
        ref_a = st.number_input("Cote Pinnacle A", min_value=1.01, value=1.80, step=0.01, format="%.2f")
        odds_a = st.number_input("Cote de votre bookmaker A", min_value=1.01, value=1.95, step=0.01, format="%.2f")
    with c2:
        name_b = st.text_input("Joueur B", "Joueur B")
        ref_b = st.number_input("Cote Pinnacle B", min_value=1.01, value=2.10, step=0.01, format="%.2f")
        odds_b = st.number_input("Cote de votre bookmaker B", min_value=1.01, value=1.90, step=0.01, format="%.2f")

    c3, c4 = st.columns(2)
    bankroll = c3.number_input("Bankroll (€)", min_value=1.0, value=1000.0, step=50.0)
    min_edge = c4.slider("Valeur minimale exigée", 0.0, 0.10, 0.02, 0.005, format="%.3f")

    res = assess_value(ref_a, ref_b, odds_a, odds_b, min_edge=min_edge, bankroll=bankroll, labels=(name_a, name_b))

    m1, m2, m3 = st.columns(3)
    m1.metric("Marge Pinnacle", pct(res.reference_margin, signed=False))
    m2.metric("Marge de votre bookmaker", pct(res.bookmaker_margin, signed=False))
    m3.metric("Mise conseillée", f"{res.stake:.2f} €")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Joueur": s.label,
                    "Probabilité juste": pct(s.fair_probability, signed=False),
                    "Cote juste": f"{s.fair_odds:.2f}",
                    "Cote proposée": f"{s.offered_odds:.2f}",
                    "Valeur": pct(s.edge),
                }
                for s in res.sides
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    if res.pick:
        p = res.pick
        st.success(
            f"**Pari à valeur : {p.label} à {p.offered_odds:.2f}** (valeur {pct(p.edge)}). "
            f"Mise conseillée : {res.stake:.2f} € (Kelly ×0,25, plafonné à 2 % de la bankroll)."
        )
    elif max(s.edge for s in res.sides) > 0.20:
        st.warning("Valeur supérieure à 20 % : vérifiez les cotes saisies, c'est presque toujours une erreur.")
    else:
        st.info(f"Pas de pari : aucune cote n'offre au moins {min_edge:.1%} de valeur.")

# --- Onglet 2 : backtest ----------------------------------------------------

with tab_backtest:
    if matches is None:
        st.info("Ajoutez au moins deux saisons dans la barre latérale pour lancer un backtest.")
    else:
        with st.form("backtest"):
            c1, c2, c3 = st.columns(3)
            model = c1.selectbox("Méthode", list(MODEL_LABELS), format_func=MODEL_LABELS.get)
            price = c2.selectbox("Cote jouée", list(PRICE_LABELS), format_func=PRICE_LABELS.get)
            haircut = c3.slider(
                "Cote × (0,97 ≈ opérateur français)", 0.90, 1.00, 1.00, 0.01, help="Simule un bookmaker moins généreux."
            )
            c4, c5, c6 = st.columns(3)
            bt_min_edge = c4.slider("Valeur minimale", 0.0, 0.10, 0.03, 0.005, format="%.3f")
            odds_range = c5.slider("Plage de cotes", 1.01, 10.0, (1.30, 4.00), 0.05)
            staking = c6.radio("Mise", ["flat", "kelly"], format_func={"flat": "Fixe (10 €)", "kelly": "Kelly ×0,25"}.get)
            first = matches["date"].min() + pd.Timedelta(days=365)
            bet_from = st.date_input(
                "Premier pari le",
                value=first.date(),
                min_value=matches["date"].min().date(),
                max_value=matches["date"].max().date(),
                help="Avant cette date, les matchs servent seulement à construire les notes Elo.",
            )
            submitted = st.form_submit_button("Lancer le backtest", type="primary")

        if submitted:
            cfg = StrategyConfig(
                model=model,
                price_source=price,
                price_haircut=haircut,
                min_edge=bt_min_edge,
                min_odds=odds_range[0],
                max_odds=odds_range[1],
                staking=staking,
            )
            with st.spinner("Backtest en cours…"):
                result = run_backtest(matches, cfg, bet_from=pd.Timestamp(bet_from))
            s = result.summary

            if not s["paris"]:
                st.warning("Aucun pari ne correspond à ces réglages.")
            else:
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Paris", f"{s['paris']:,}".replace(",", " "))
                m2.metric("Gain net", f"{s['gain_net']:+,.2f} €".replace(",", " "))
                m3.metric("ROI", pct(s["roi"]))
                m4.metric("CLV moyen", pct(s["clv_moyen"]) if s["clv_moyen"] == s["clv_moyen"] else "n/d")
                m5.metric("Drawdown max", pct(s["drawdown_max"], signed=False))

                if s["t_stat"] > 2:
                    st.success(f"Statistique t = {s['t_stat']:.2f} : résultat difficilement attribuable à la chance.")
                else:
                    st.warning(
                        f"Statistique t = {s['t_stat']:.2f} : impossible de distinguer l'avantage de la chance."
                    )

                st.subheader("Évolution de la bankroll")
                st.line_chart(result.bets.set_index("date")["bankroll"], y_label="Bankroll (€)")

                c1, c2 = st.columns(2)
                c1.subheader("Par année")
                c1.dataframe(result.by_year, width="stretch")
                c2.subheader("Par surface")
                c2.dataframe(result.by_surface, width="stretch")

                if result.calibration:
                    c = result.calibration
                    st.caption(
                        f"Précision sur {c['matchs']} matchs : log-loss Elo {c['log_loss_elo']:.4f}, "
                        f"Pinnacle {c['log_loss_pinnacle']:.4f} (plus bas = meilleur)."
                    )

                st.download_button(
                    "Télécharger le détail des paris (CSV)",
                    result.bets.to_csv(index=False).encode("utf-8"),
                    file_name="paris_backtest.csv",
                    mime="text/csv",
                )

# --- Onglet 3 : classement et prédiction Elo -------------------------------

with tab_elo:
    if matches is None:
        st.info("Ajoutez des saisons dans la barre latérale pour calculer le classement Elo.")
    else:
        key = f"{len(matches)}-{matches['date'].max()}"
        elo = build_elo(matches, key)
        st.warning(
            "Sur 2021-2025, l'Elo est nettement moins précis que Pinnacle : "
            "à utiliser comme repère, pas pour décider d'un pari."
        )
        c1, c2 = st.columns([1, 2])
        with c1:
            surface = st.selectbox("Surface", [None, *SURFACES], format_func=lambda s: "Toutes" if s is None else SURFACE_LABELS[s])
            top = st.slider("Nombre de joueurs", 10, 100, 25, 5)
        ranking = pd.DataFrame(elo.top(top, surface), columns=["Joueur", "Note", "Matchs"])
        ranking.index = range(1, len(ranking) + 1)
        ranking["Note"] = ranking["Note"].round(0).astype(int)
        c2.dataframe(ranking, width="stretch")

        st.subheader("Face-à-face")
        players = [n for n, _, m in elo.top(10_000) if m >= 10]  # triés par note : les favoris en premier
        if len(players) >= 2:
            f1, f2, f3, f4 = st.columns(4)
            pa = f1.selectbox("Joueur A", players, index=0)
            pb = f2.selectbox("Joueur B", players, index=1)
            surf = f3.selectbox("Surface du match", SURFACES, format_func=SURFACE_LABELS.get)
            bo = f4.radio("Format", [3, 5], format_func=lambda b: f"{b} sets", horizontal=True)
            if pa != pb:
                p = elo.predict(pa, pb, surf, bo)
                st.metric(f"Probabilité Elo que {pa} gagne", pct(p, signed=False), help=f"Cote juste : {1 / p:.2f}")
