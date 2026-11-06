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
| `python -m pytest` | Lance les tests |

Les commandes `pronounce`, `build-episode`, `build-week` et `compile` arrivent aux étapes suivantes.

## Choisir les voix

1. `python -m bongo voices` (le modèle se télécharge la première fois).
2. Ouvrir la page indiquée (`out\voices\...\ecoute.html`) et écouter.
3. Écrire les noms choisis dans `config.yaml`, rubrique `voices` (par exemple `voice: "am_michael"`).
   Ces réglages ne changent plus ensuite : Bongo doit sonner pareil du 1er au 28 décembre.
