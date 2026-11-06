# Préparer les vrais dessins

Le moteur assemble des calques PNG transparents. Tant qu'un dessin manque, `python -m bongo placeholders`
met une forme provisoire à sa place ; dès que tu enregistres un vrai dessin au même nom, il est utilisé
(les vrais dessins ne sont jamais écrasés). `python -m bongo check-setup` compte les provisoires restants.

## Bongo — `assets/characters/bongo/`

Tous les calques du corps ont **la même taille de toile** (par exemple 700 × 900 px) et Bongo y est
toujours à la même place : les pieds au même point, en bas au centre.

| Dossier | Fichiers | Contenu |
| --- | --- | --- |
| `body/` | `stand`, `arms_up`, `drum_a`, `drum_b`, `point`, `crouch`, `sleep` | Corps complet avec la tête et le visage **sans** yeux, sourcils ni bouche |
| `eyes/` | `open`, `half`, `closed`, `left`, `right` | Les deux yeux sur un petit calque (regard à gauche = vers la gauche de l'image) |
| `brows/` | `neutral`, `surprised` | Les deux sourcils |
| `mouth/` | `A` à `H`, `X` | Les 9 bouches de Rhubarb (voir le README de Rhubarb pour chaque forme) |

Les petits calques (yeux, sourcils, bouche) sont posés **centrés** sur un point d'ancrage du visage.

## Chaque ami — `assets/characters/<animal>/`

`pose_1`, `pose_2` (même toile), `eyes_open`, `eyes_closed`, `mouth_closed`, `mouth_half`, `mouth_open`.

## `rig.json`

Les coordonnées sont en pixels, dans la toile du corps (0,0 = coin en haut à gauche).

```json
{
  "canvas": [700, 900],
  "feet": [350, 885],
  "face": {
    "stand":   {"eyes": [350, 250], "brows": [350, 185], "mouth": [350, 345]},
    "crouch":  {"eyes": [350, 390], "brows": [350, 325], "mouth": [350, 485]}
  },
  "eyes_closed_in": ["sleep"]
}
```

- `feet` : le point posé sur le sol (centre des pieds).
- `face` : pour **chaque pose**, le centre des yeux, des sourcils (Bongo seulement) et de la bouche.
  Pour un ami : `pose_1` et `pose_2`, avec `eyes` et `mouth`.
- `eyes_closed_in` : poses où Bongo a toujours les yeux fermés (il dort).

Astuce : dans Inkscape, place un repère sur chaque centre et lis ses coordonnées (axe Y vers le bas).

## Décors et cartes

- `assets/backgrounds/<milieu>/<décor>.png` en 2560 × 1440 (le nid, commun à tous : `assets/backgrounds/common/nest.png`).
  Laisser de l'espace libre en bas : les personnages ont les pieds à 96 % de la hauteur.
- `assets/cards/<mot>.png` : l'image seule, carrée, fond transparent ou uni ; le mot écrit est ajouté automatiquement.

## Vérifier un dessin

```
python -m bongo check-setup
python -m bongo render 3 --image 40
```

La deuxième commande enregistre l'image de la 40e seconde de l'épisode 3 dans `episodes\ep003\`.
