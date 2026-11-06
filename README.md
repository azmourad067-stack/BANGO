# Bongo the Gorilla — fabrication des épisodes

Système qui fabrique, par lots d'une semaine, les épisodes de la chaîne YouTube « Bongo the Gorilla ».
Les règles du projet sont dans [CLAUDE.md](CLAUDE.md) ; le programme de la saison dans `content/curriculum.yaml`.

## Installation (Windows 11, une seule fois)

1. **Python 3.12** : https://www.python.org/downloads/ — prendre une version 3.12 (Kokoro ne fonctionne pas
   avec 3.13). Pendant l'installation, cocher « Add python.exe to PATH ».
2. **FFmpeg** : ouvrir PowerShell et taper `winget install Gyan.FFmpeg`.
3. **espeak-ng** (prononciation des mots rares) : installer le fichier `.msi` le plus récent depuis
   https://github.com/espeak-ng/espeak-ng/releases
4. **Rhubarb Lip Sync** : suivre `tools/rhubarb/LISEZMOI.txt`.
5. **Bongo** : double-cliquer sur `installer.bat`. Il crée l'environnement `.venv`, installe tout
   (quelques Go : PyTorch est inclus) et lance la vérification.
6. **Clé Gemini** (gratuite) : https://aistudio.google.com/apikey — ouvrir le fichier `.env` avec le Bloc-notes
   et coller la clé après `GEMINI_API_KEY=`.

## Utilisation

Ouvrir un terminal dans le dossier du projet, puis activer l'environnement :

```
.venv\Scripts\activate
```

| Commande | Rôle |
| --- | --- |
| `python -m bongo check-setup` | Vérifie l'installation : outils, clé, voix choisies, assets de chaque milieu |
| `python -m bongo programme` | Affiche le programme de la saison |
| `python -m bongo placeholders` | Crée des dessins provisoires (formes simples) ; ne touche jamais aux vrais dessins |
| `python -m bongo voices` | Fait dire « Hello, little explorer! » par les 20 voix américaines de Kokoro |
| `python -m bongo voices --text "Boom, boom, boom!" --voices am_michael,am_adam` | Même chose, avec une autre phrase et quelques voix |
| `python -m bongo check-script content\examples\ep003_frog_leaf.json` | Contrôle un scénario écrit à la main |
| `python -m bongo pronounce` | Fait dire les 48 mots du programme par la voix de Bongo (page d'écoute avec les phonèmes) |
| `python -m bongo build-episode 3` | Fabrique l'épisode 3 complet : scénario, voix, contrôles, image, son mixé, sous-titres, miniature, métadonnées, rapport |
| `python -m bongo build-episode 3 --script-file content\examples\ep003_frog_leaf.json` | Même chose avec un scénario écrit à la main (sans Gemini) |
| `python -m bongo build-episode 3 --new-script` | Redemande un scénario à Gemini (sinon le précédent est réutilisé) |
| `python -m bongo build-episode 3 --no-video` | S'arrête au son (plus rapide) |
| `python -m bongo render 3` | Refait seulement l'image (après avoir changé un dessin) : aperçu avec les voix seules |
| `python -m bongo report --start 2026-12-01` | Refait le rapport de la semaine |
| `python -m bongo render 3 --image 40` | Une seule image, à la 40e seconde (pour vérifier un dessin) |
| `python -m bongo render 3 --script-file content\examples\ep003_frog_leaf.json` | Maquette muette, sans les voix |
| `python -m pytest` | Lance les tests |

Résultat : `out\week_2026-12-01\` contient la vidéo, les sous-titres, la miniature et `report.html`,
où l'on copie le titre, la description et les tags dans YouTube Studio. Un épisode bloqué par les
contrôles n'y est pas copié. `build-week` et `compile` arrivent à l'étape 5.

Dans `episodes\ep003\` : `script.json` (scénario), `audio\` (une réplique = un WAV),
`lipsync\` (bouches), `timeline.json` (minutage), `voice.wav` (voix placées), `video.mp4` (image seule),
`ep003.mp4` (épisode final), `ep003.srt`, `thumb.png`, `metadata.json`,
`qa.json` (résultat des contrôles), `rejected\` (scénarios refusés par les contrôles).

Pour remplacer les dessins provisoires par les vrais : voir [docs/DESSINS.md](docs/DESSINS.md).
Relancer la commande réutilise tout ce qui est déjà fait.

## Corriger une prononciation

1. `python -m bongo pronounce`, puis ouvrir `out\pronounce\ecoute.html`.
2. Pour un mot mal dit, copier ses phonèmes affichés, les corriger, et ajouter une ligne dans
   `content\pronunciations.yaml`, par exemple `goodnight: "ɡʊdnˈIt"`.
3. Relancer `python -m bongo pronounce --words goodnight` pour réécouter.

## Voix

Une voix est déjà choisie pour chaque personnage dans `config.yaml` (Bongo : `am_michael`).
Pour les réécouter ou en essayer d'autres : `python -m bongo voices`, puis ouvrir `out\voices\...\ecoute.html`.
Changer une voix uniquement avant le 1er décembre : ensuite, Bongo doit sonner pareil tous les jours.

## Musique, bruitages et comptines

| Dossier | Fichiers | Source |
| --- | --- | --- |
| `assets\audio\music\` | `jungle.mp3`, `forest.mp3`, `river.mp3`, `mountain.mp3` (ou `default.mp3`) | Bibliothèque audio de YouTube Studio, morceaux doux |
| `assets\audio\sfx\` | `card` (apparition d'une carte), `jump` (saut), `drum` (tambour) | Sons CC0 uniquement |
| `assets\audio\chants\` | `hello`, `goodbye` (facultatifs) | Ta voix, ou Bongo en comptine |

Formats acceptés : .mp3, .wav, .ogg, .m4a, .flac. Un vrai fichier est toujours préféré au son provisoire du même nom. Chaque fichier ajouté se note dans `LICENSES.md` (source, licence, date).
La musique est réglée 20 dB sous la voix et s'arrête pendant les pauses où l'enfant répond ;
le volume final est normalisé à -14 LUFS.
