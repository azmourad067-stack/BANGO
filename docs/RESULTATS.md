# Résultats des backtests ATP 2021-2025

Données : 13 171 matchs ATP (tennis-data.co.uk), cotes de clôture Bet365, Pinnacle, moyenne et maximum du marché. Mise fixe de 10 €, bankroll de 1 000 €. Les abandons et forfaits ne sont pas joués.

## 1. Le modèle Elo seul ne bat pas le marché

Paris de 2022 à 2025, valeur minimale de 3 % :

| Cote jouée | Paris | ROI | CLV moyen | Statistique t |
|---|---|---|---|---|
| Bet365 | 2 156 | -5,8 % | -5,2 % | -3,2 |
| Bet365 × 0,97 (opérateur français) | 1 843 | -9,6 % | -8,1 % | -4,2 |
| Moyenne du marché | 2 145 | -6,1 % | -5,8 % | -3,5 |

Précision sur 2023-2025, saisons jamais vues pendant le réglage : log-loss Elo 0,626 contre Pinnacle 0,593. Plus bas est meilleur, et l'écart est large.

Démarrer les joueurs à partir de leur classement ATP et régler les paramètres sur 2021-2022 n'y change rien. Une régression logistique montre que l'Elo et le classement **n'apportent aucune information** en plus de la cote Pinnacle : la cote Pinnacle sans marge est déjà bien calibrée (coefficient 1,01).

Le modèle de mélange Elo + marché perd lui aussi : -4,9 % sur Bet365.

## 2. Comparer chaque bookmaker à Pinnacle fonctionne mieux

On prend la cote Pinnacle sans sa marge comme vraie probabilité, et on parie quand un autre bookmaker paie plus. Paris de 2021 à 2025, cotes 1,30 à 4,00 :

| Cote jouée | Valeur min. | Paris | ROI | Stat. t | Années négatives |
|---|---|---|---|---|---|
| Meilleure cote du marché | 2 % | 3 578 | +6,9 % | 3,7 | 2023 (-0,9 %) |
| Meilleure cote du marché | 3 % | 2 552 | +7,9 % | 3,4 | 2023 (-4,1 %) |
| Bet365 | 1 % | 896 | +7,5 % | 1,9 | 2022 (-1,6 %) |
| Bet365 | 3 % | 352 | +9,7 % | 1,4 | 2022 (-11 %) |
| Bet365 × 0,97 | 3 % | 69 | +3,6 % | 0,2 | — |
| Cote moyenne | 2 % | 82 | +7,9 % | 0,6 | 2021, 2022 |

## 3. Ce qu'il faut en retenir

- Le seul résultat statistiquement solide (t > 3) suppose de jouer la **meilleure cote du marché**. Cela demande des comptes chez de nombreux bookmakers internationaux, non agréés en France, et ces cotes « maximum » de clôture contiennent des prix périmés ou erronés impossibles à obtenir en réalité.
- Sur Bet365 seul, le résultat est positif mais pas encore significatif (t < 2).
- Avec des cotes d'opérateur français (environ 3 % plus basses), il ne reste presque aucun pari : la marge réglementée en France efface l'avantage.
- Les cotes historiques sont toutes des cotes de clôture : en réalité, il faut repérer l'écart avant que le bookmaker ne corrige sa cote.

## 4. Utilisation pratique

Pour un match à venir, relevez la cote Pinnacle sur un comparateur de cotes et la cote de votre bookmaker, puis :

```bash
python -m bango value --ref 1.80 2.10 --odds 1.95 1.90
```

Notez chaque pari dans le tableur de suivi et surveillez le CLV moyen sur au moins 300 paris.
