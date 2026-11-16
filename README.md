# BANGO

Moteur de *value betting* pour le **tennis** (ATP/WTA).

Le principe : estimer la vraie probabilité de victoire de chaque joueur, la comparer à la cote du bookmaker, et ne parier que lorsque la cote paie plus que le risque réel. Le moteur rejoue ensuite cette stratégie sur des années d'historique pour vérifier, chiffres à l'appui, si elle aurait gagné de l'argent.

## Ce que fait le moteur

| Module | Rôle |
|---|---|
| `bango/elo.py` | Note Elo de chaque joueur, globale et par surface (dur, terre, gazon). Ajustement pour les matchs en 3 sets gagnants. |
| `bango/odds.py` | Probabilités implicites, retrait de la marge du bookmaker, valeur attendue, critère de Kelly. |
| `bango/strategy.py` | Règles de sélection (valeur minimale et maximale, plage de cotes, historique minimal) et de mise (fixe ou Kelly fractionné, plafond 2 %). |
| `bango/backtest.py` | Rejoue l'historique match par match, sans jamais utiliser d'information future. Calcule ROI, drawdown, CLV, significativité. |
| `bango/data.py` | Lit les fichiers de [tennis-data.co.uk](http://www.tennis-data.co.uk/alldata.php). |
| `bango/cli.py` | Ligne de commande. |

Trois façons d'estimer la probabilité (`--model`) :

- `elo` : uniquement notre modèle.
- `market` : la cote Pinnacle sans sa marge. Pinnacle est le bookmaker le plus juste du marché : parier quand un autre bookmaker propose mieux que Pinnacle est la méthode de value betting la plus éprouvée.
- `blend` : mélange des deux (30 % Elo, 70 % marché par défaut).

## Installation

```bash
pip install -e ".[dev]"
```

## Données

Téléchargez les saisons ATP (fichiers `.xlsx`) sur <http://www.tennis-data.co.uk/alldata.php> et placez-les dans `data/`. Prenez au moins 3 saisons : la première sert uniquement à construire les notes Elo.

## Utilisation

```bash
# Démonstration sur données simulées (aucun téléchargement nécessaire)
python -m bango demo

# Backtest sur l'historique réel
python -m bango backtest data/2021.xlsx data/2022.xlsx data/2023.xlsx data/2024.xlsx --model blend

# Simuler un opérateur français (cotes ~3 % plus basses que Bet365)
python -m bango backtest data/*.xlsx --model market --haircut 0.97

# Exporter chaque pari pour l'analyser dans le tableur de suivi
python -m bango backtest data/*.xlsx --export paris.csv

# Analyser un match à venir
python -m bango predict data/*.xlsx --a "Sinner J." --b "Alcaraz C." --surface Clay --odds-a 1.95 --odds-b 1.95

# Classement Elo sur terre battue
python -m bango ranking data/*.xlsx --surface Clay --top 20
```

## Lire les résultats

- **ROI** : gain net divisé par la somme misée.
- **CLV** (*closing line value*) : notre cote comparée au prix juste de Pinnacle juste avant le match. Un CLV moyen positif sur des centaines de paris est le meilleur indicateur d'un avantage réel, bien plus fiable que le ROI à court terme.
- **Statistique t** : en dessous de 2, le résultat peut s'expliquer par la chance.
- **Log-loss Elo vs Pinnacle** : si l'Elo fait moins bien que Pinnacle (c'est le cas habituel), il ne faut pas parier sur l'Elo seul contre des cotes justes.

## Limites connues

- Les cotes historiques sont des cotes de clôture : en réalité, on parie plus tôt, à d'autres prix.
- Les bookmakers grand public limitent rapidement les comptes gagnants.
- Le modèle ignore blessures, fatigue, motivation et conditions de jeu. Les valeurs supérieures à 20 % sont écartées, car elles viennent presque toujours de là.
- Un bon backtest ne garantit pas les résultats futurs.

## Application web (Streamlit)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Quatre onglets :

- **Programme** : matchs ATP/WTA à venir avec les cotes en direct de Pinnacle et des bookmakers français (Winamax, Betclic, Unibet, NetBet, Parions Sport, PMU), récupérées via [The Odds API](https://the-odds-api.com). Les paris à valeur et la mise conseillée sont calculés automatiquement.
- **Analyser un match** : saisie manuelle des cotes.
- **Backtest** : glissez vos fichiers de saison dans la barre latérale.
- **Classement Elo**.

### Clé The Odds API

L'onglet Programme a besoin d'une clé gratuite (environ 500 requêtes par mois) créée sur <https://the-odds-api.com>. Chaque actualisation coûte 2 requêtes par tournoi en cours (régions `eu` pour Pinnacle et `fr` pour les opérateurs français) ; les cotes sont gardées 10 minutes.

- En local : copiez `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml` (non versionné) et collez-y votre clé, ou définissez la variable d'environnement `ODDS_API_KEY`.
- Sur Streamlit Community Cloud : **Settings → Secrets**, puis ajoutez `ODDS_API_KEY = "votre-cle"`.

### Déployer sur Streamlit Community Cloud

1. Connectez-vous sur <https://share.streamlit.io> avec votre compte GitHub.
2. **Create app** → choisissez le dépôt `BANGO`, la branche, et le fichier `streamlit_app.py`.
3. **Deploy**. Les dépendances sont lues dans `requirements.txt`.

Les fichiers de données ne sont pas dans le dépôt : chaque utilisateur charge ses saisons depuis la barre latérale.
