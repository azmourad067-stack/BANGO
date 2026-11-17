"""Interface web de BANGO. Lancement local : ``streamlit run streamlit_app.py``."""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from bango.backtest import run_backtest
from bango.data import normalize
from bango.elo import SurfaceElo
from bango import journal as journal_mod
from bango.schedule import (
    DEFAULT_LEAGUES,
    SPORTS,
    OddsApiClient,
    OddsApiError,
    UpcomingMatch,
    load_snapshot,
    match_player,
)
from bango.strategy import StrategyConfig
from bango.value import assess_value

st.set_page_config(page_title="BANGO · Value betting", page_icon="🎯", layout="wide")

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


@st.cache_data(ttl=3600, show_spinner="Liste des compétitions…")
def fetch_competitions(api_key: str) -> list[dict]:
    return OddsApiClient(api_key).competitions()  # appel gratuit


def fetch_events(api_key: str, keys: tuple[str, ...]) -> tuple[list[UpcomingMatch], str | None]:
    client = OddsApiClient(api_key)
    return client.upcoming(list(keys)), client.requests_remaining


def configured_api_key() -> str:
    try:
        key = st.secrets.get("ODDS_API_KEY", "")
    except Exception:  # pas de fichier de secrets en local
        key = ""
    return key or os.environ.get("ODDS_API_KEY", "")


def pct(x: float, signed: bool = True) -> str:
    return f"{x * 100:+.1f} %" if signed else f"{x * 100:.1f} %"


# --- Barre latérale : données historiques ---------------------------------

with st.sidebar:
    st.header("Données historiques")
    st.caption(
        "Fichiers de saison ATP et/ou WTA au format tennis-data.co.uk (.xlsx). "
        "Nécessaires pour le backtest et le classement Elo, pas pour l'analyse d'un match."
    )
    uploads = st.file_uploader("Saisons", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    matches = None
    if uploads:
        try:
            matches = load_files(tuple((f.name, f.getvalue()) for f in uploads))
            count = f"{len(matches):,}".replace(",", " ")
            per_tour = " · ".join(f"{t.upper()} {n:,}".replace(",", " ") for t, n in matches["tour"].value_counts().items())
            st.success(
                f"{count} matchs ({per_tour}), du {matches['date'].min():%d/%m/%Y} au {matches['date'].max():%d/%m/%Y}"
            )
        except ValueError as exc:
            st.error(f"Fichier illisible : {exc}")
    st.divider()
    st.caption(
        "Les paris comportent des risques : endettement, dépendance. "
        "Joueurs Info Service : 09 74 75 13 13 (appel non surtaxé)."
    )

st.title("BANGO")
st.caption("Value betting : ne parier que lorsque la cote paie plus que le risque réel. Tennis, football, basket.")

tab_schedule, tab_journal, tab_value, tab_backtest, tab_elo = st.tabs(
    ["Programme", "Journal", "Analyser un match", "Backtest", "Classement Elo"]
)

# --- Onglet : programme et cotes en direct ----------------------------------

PARIS = ZoneInfo("Europe/Paris")
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
JOURNAL_PATH = Path(__file__).resolve().parent / "data" / "journal.csv"
SNAPSHOT_PATH = Path(os.environ.get("BANGO_SNAPSHOT", Path(__file__).resolve().parent / "data" / "latest.json"))


def when(dt) -> str:
    local = dt.astimezone(PARIS)
    return f"{JOURS[local.weekday()]} {local:%d/%m %H:%M}"


@st.cache_data(show_spinner=False)
def read_snapshot(path: str, mtime: float):
    return load_snapshot(path)  # ``mtime`` sert seulement à relire le fichier quand il change


with tab_schedule:
    snapshot = read_snapshot(str(SNAPSHOT_PATH), SNAPSHOT_PATH.stat().st_mtime) if SNAPSHOT_PATH.exists() else None
    live = st.session_state.get("programme")

    c1, c2 = st.columns([1, 1])
    sports = c1.multiselect("Sports", list(SPORTS), default=list(SPORTS), format_func=SPORTS.get)
    tour = c2.radio(
        "Tennis",
        [None, "atp", "wta"],
        format_func=lambda t: "ATP + WTA" if t is None else t.upper(),
        horizontal=True,
        disabled="tennis" not in sports,
    )

    with st.expander("Actualiser les cotes maintenant (consomme des crédits)", expanded=snapshot is None):
        api_key = configured_api_key()
        if not api_key:
            st.info(
                "Le programme des matchs et les cotes viennent de **The Odds API** (offre gratuite d'environ "
                "500 requêtes par mois). Créez une clé sur https://the-odds-api.com, puis ajoutez-la dans les "
                "secrets de l'application sous le nom `ODDS_API_KEY`, ou collez-la ci-dessous pour cette session."
            )
            api_key = st.text_input("Clé The Odds API", type="password")
        if api_key:
            try:
                comps = fetch_competitions(api_key)  # appel gratuit
            except OddsApiError as exc:
                st.error(str(exc))
                comps = []
            except Exception as exc:  # réseau indisponible, réponse inattendue
                st.error(f"Impossible de joindre The Odds API : {exc}")
                comps = []
            if comps:
                leagues_available = {c["key"]: c["title"] for c in comps if c["sport"] in ("football", "basket")}
                leagues = st.multiselect(
                    "Ligues de football et de basket",
                    sorted(leagues_available, key=lambda k: (not k.startswith("soccer"), leagues_available[k])),
                    default=[k for k in DEFAULT_LEAGUES if k in leagues_available],
                    format_func=leagues_available.get,
                    help="Chaque ligue coûte 1 requête par actualisation.",
                )
                chosen = [
                    c["key"]
                    for c in comps
                    if c["sport"] in sports
                    and (
                        (c["sport"] == "tennis" and (tour is None or c["key"].startswith(f"tennis_{tour}")))
                        or c["key"] in leagues
                    )
                ]
                c3, c4 = st.columns([1, 3])
                if c3.button(f"Actualiser ({len(chosen)} crédits)", type="primary", disabled=not chosen):
                    with st.spinner("Récupération des cotes…"):
                        try:
                            fetched, left = fetch_events(api_key, tuple(chosen))
                            live = st.session_state["programme"] = (fetched, left, datetime.now(timezone.utc))
                        except OddsApiError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Impossible de joindre The Odds API : {exc}")
                c4.caption(
                    f"{len(chosen)} compétition(s) sélectionnée(s), 1 crédit chacune. "
                    "Inutile de cliquer pour consulter les cotes du dernier relevé automatique."
                )

    if live:
        upcoming, remaining, loaded_at = live
        st.caption(f"Cotes actualisées manuellement le {when(loaded_at)}.")
    elif snapshot:
        upcoming, loaded_at, remaining = snapshot
        st.caption(
            f"Cotes du dernier relevé automatique, le {when(loaded_at)} (relevés vers 10 h 37 et 17 h 53). "
            "Les consulter ne consomme aucun crédit."
        )
    else:
        upcoming, remaining = [], None
    now = datetime.now(timezone.utc)
    upcoming = [
        m
        for m in upcoming
        if m.start > now  # un match commencé ne se joue plus avant le coup d'envoi
        and m.sport in sports
        and (m.sport != "tennis" or tour is None or m.tour == tour)
    ]
    if remaining is not None:
        st.caption(f"Requêtes restantes ce mois-ci : {remaining}")

    if upcoming:
        all_books = {k: b.title for m in upcoming for k, b in m.books.items() if k != "pinnacle"}
        c5, c6, c7 = st.columns([2, 1, 1])
        my_books = c5.multiselect(
            "Mes bookmakers",
            sorted(all_books),
            default=sorted(all_books),
            format_func=lambda k: all_books[k],
            help="Pour chaque issue, la meilleure cote est cherchée parmi ces bookmakers.",
        )
        sched_edge = c6.slider("Valeur minimale", 0.0, 0.10, 0.02, 0.005, format="%.3f", key="sched_edge")
        sched_bankroll = c7.number_input("Bankroll (€)", min_value=1.0, value=1000.0, step=50.0, key="sched_bk")
        only_value = st.toggle("Afficher seulement les paris à valeur", value=False)

        elo = build_elo(matches, f"{len(matches)}-{matches['date'].max()}") if matches is not None else None
        known = [n for n, _, m in elo.top(100_000) if m >= 10] if elo else []

        rows = []
        no_reference = 0
        for m in upcoming:
            res = m.assess(my_books, min_edge=sched_edge, bankroll=sched_bankroll)
            if res is None:
                no_reference += 1
                continue
            if only_value and not res.pick:
                continue
            sport = SPORTS.get(m.sport, m.sport)
            row = {
                "Heure": when(m.start),
                "Sport": f"Tennis {m.tour.upper()}" if m.sport == "tennis" else sport,
                "Match": m.label,
                "Pari conseillé": (
                    f"{res.pick.label} à {res.pick.offered_odds:.2f} ({res.pick.bookmaker})" if res.pick else "—"
                ),
                "Mise": f"{res.stake:.2f} €" if res.pick else "",
                "Valeurs": " / ".join(pct(sd.edge) for sd in res.sides),
                "Pinnacle": " / ".join(f"{m.reference.price(o):.2f}" for o in m.outcomes),
                "Meilleures cotes": " / ".join(f"{sd.offered_odds:.2f} ({sd.bookmaker})" for sd in res.sides),
                "Compétition": m.tournament,
            }
            if elo and m.sport == "tennis":
                ea, eb = match_player(m.player_a, known), match_player(m.player_b, known)
                row["Elo (1er joueur)"] = pct(elo.predict(ea, eb, m.surface), signed=False) if ea and eb else "n/d"
            rows.append(row)

        n_value = sum(1 for r in rows if r["Pari conseillé"] != "—")
        st.markdown(f"**{len(rows)} matchs analysés, {n_value} pari(s) à valeur.**")
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if no_reference:
            st.caption(
                f"{no_reference} match(s) ignoré(s) : pas de cote Pinnacle ou aucune cote chez vos bookmakers."
            )
        st.caption(
            "Football : les valeurs se lisent dans l'ordre domicile / nul / extérieur. "
            "Les cotes bougent vite : vérifiez toujours la cote chez votre bookmaker avant de parier."
        )
    elif live or snapshot:
        st.info("Aucun match avec des cotes pour cette sélection pour le moment.")

# --- Onglet : journal des opportunités -------------------------------------

with tab_journal:
    journal = journal_mod.load(JOURNAL_PATH)
    if journal.empty:
        st.info(
            "Le journal est vide. Il se remplit avec la commande `python -m bango scan`, "
            "lancée chaque jour automatiquement par GitHub Actions une fois le relevé activé (voir le README)."
        )
    else:
        j_edge = st.slider("Compter les paris dont la valeur atteint au moins", 0.0, 0.10, 0.02, 0.005, format="%.3f")
        counts = journal_mod.daily_counts(journal, j_edge)
        first, last = journal["first_seen"].min(), journal["last_seen"].max()
        days = max(1, (last.tz_convert(PARIS).date() - first.tz_convert(PARIS).date()).days + 1)
        total = int(counts["total"].sum()) if not counts.empty else 0
        k1, k2, k3 = st.columns(3)
        k1.metric("Période suivie", f"{days} jour(s)")
        k2.metric("Paris à valeur repérés", total)
        k3.metric("Moyenne par jour", f"{total / days:.1f}")
        st.caption(f"Du {when(first)} au {when(last)}. Un seul pari compté par match.")
        if not counts.empty:
            per_sport = counts.drop(columns="total").sum().rename(index=SPORTS)
            st.subheader("Par jour et par sport")
            st.bar_chart(counts.drop(columns="total").rename(columns=SPORTS))
            st.dataframe((per_sport / days).round(2).rename("Paris par jour").to_frame(), width="content")
        st.subheader("Dernières opportunités")
        recent = journal[journal["best_edge"] >= j_edge].sort_values("first_seen", ascending=False).head(50)
        st.dataframe(
            pd.DataFrame(
                {
                    "Repéré": recent["first_seen"].map(when),
                    "Sport": recent["sport"].map(SPORTS),
                    "Match": recent["match"],
                    "Pari": recent["pick"],
                    "Bookmaker": recent["bookmaker"],
                    "Cote": recent["odds"],
                    "Cote juste": recent["fair_odds"],
                    "Meilleure valeur": recent["best_edge"].map(pct),
                    "Vu": recent["seen"],
                }
            ),
            hide_index=True,
            width="stretch",
        )
        st.download_button(
            "Télécharger le journal (CSV)", JOURNAL_PATH.read_bytes(), file_name="journal.csv", mime="text/csv"
        )

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
        tours_loaded = sorted(matches["tour"].unique())
        with st.form("backtest"):
            bt_tour = None
            if len(tours_loaded) > 1:
                bt_tour = st.radio(
                    "Circuit",
                    [None, *tours_loaded],
                    format_func=lambda t: "ATP + WTA" if t is None else t.upper(),
                    horizontal=True,
                )
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
                bt_matches = matches if bt_tour is None else matches[matches["tour"] == bt_tour].reset_index(drop=True)
                result = run_backtest(bt_matches, cfg, bet_from=pd.Timestamp(bet_from))
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
            "Sur l'ATP 2021-2025, l'Elo est nettement moins précis que Pinnacle : "
            "à utiliser comme repère, pas pour décider d'un pari."
        )
        tour_players = {t: set(matches.loc[matches["tour"] == t, "winner"]) | set(matches.loc[matches["tour"] == t, "loser"])
                        for t in matches["tour"].unique()}
        c1, c2 = st.columns([1, 2])
        with c1:
            elo_tour = st.radio("Circuit", sorted(tour_players), format_func=str.upper, horizontal=True, key="elo_tour")
            surface = st.selectbox("Surface", [None, *SURFACES], format_func=lambda s: "Toutes" if s is None else SURFACE_LABELS[s])
            top = st.slider("Nombre de joueurs", 10, 100, 25, 5)
        in_tour = [r for r in elo.top(100_000, surface) if r[0] in tour_players[elo_tour]]
        ranking = pd.DataFrame(in_tour[:top], columns=["Joueur", "Note", "Matchs"])
        ranking.index = range(1, len(ranking) + 1)
        ranking["Note"] = ranking["Note"].round(0).astype(int)
        c2.dataframe(ranking, width="stretch")

        st.subheader("Face-à-face")
        # Triés par note : les favoris en premier. Un face-à-face se joue dans un seul circuit.
        players = [n for n, _, m in elo.top(100_000) if m >= 10 and n in tour_players[elo_tour]]
        if len(players) >= 2:
            f1, f2, f3, f4 = st.columns(4)
            pa = f1.selectbox("Joueur A", players, index=0)
            pb = f2.selectbox("Joueur B", players, index=1)
            surf = f3.selectbox("Surface du match", SURFACES, format_func=SURFACE_LABELS.get)
            bo = f4.radio("Format", [3, 5], format_func=lambda b: f"{b} sets", horizontal=True)
            if pa != pb:
                p = elo.predict(pa, pb, surf, bo)
                st.metric(f"Probabilité Elo que {pa} gagne", pct(p, signed=False), help=f"Cote juste : {1 / p:.2f}")
