# Registre des licences

La chaîne sera monétisée : chaque dépendance, asset, musique et bruitage doit autoriser l'usage commercial.
Une ligne par élément. Pour les musiques et bruitages : source, licence et date de téléchargement.

## Logiciels

| Élément | Rôle | Licence | Usage commercial | Remarque |
| --- | --- | --- | --- | --- |
| Python | Langage | PSF | Oui | |
| PyYAML | Configuration | MIT | Oui | |
| pydantic | Validation | MIT | Oui | |
| Pillow | Image | MIT-CMU (HPND) | Oui | |
| numpy | Calcul | BSD-3-Clause | Oui | |
| Jinja2 | Rapport HTML | BSD-3-Clause | Oui | |
| pytest | Tests | MIT | Oui | Développement uniquement |
| Kokoro (`kokoro`) | Voix | Apache 2.0 | Oui | Python 3.10 à 3.12 |
| Modèle Kokoro-82M (hexgrad) | Voix | Apache 2.0 | Oui | Téléchargé depuis Hugging Face |
| misaki | Phonétisation (dépendance de Kokoro) | Apache 2.0 | Oui | |
| PyTorch | Dépendance de Kokoro | BSD-3-Clause | Oui | |
| espeak-ng | Phonétisation des mots rares | GPL-3.0 | Oui | Programme séparé, appelé par Kokoro ; non redistribué |
| soundfile | Lecture/écriture audio | BSD-3-Clause | Oui | |
| faster-whisper | Contrôle de prononciation | MIT | Oui | |
| Modèle Whisper small.en (Systran/faster-whisper-small.en) | Contrôle | MIT | Oui | Conversion du modèle OpenAI Whisper (MIT) |
| google-genai | SDK Gemini | Apache 2.0 | Oui | Palier gratuit : les requêtes peuvent servir à Google, aucune donnée personnelle |
| Rhubarb Lip Sync | Bouches | MIT | Oui | À confirmer avec le fichier LICENSE.md livré dans l'archive Windows |
| FFmpeg (build Windows) | Vidéo et audio | LGPL/GPL | Oui | Programme séparé, non redistribué |

## Polices

| Élément | Licence | Source | Remarque |
| --- | --- | --- | --- |
| Fredoka (`assets/fonts/Fredoka.ttf`) | SIL OFL 1.1 | github.com/google/fonts (ofl/fredoka) | Licence dans `assets/fonts/OFL.txt` |

## Dessins

| Élément | Auteur / outil | Licence | Date |
| --- | --- | --- | --- |
| Assets provisoires (`python -m bongo placeholders`) | Générés par le projet | Propriété du projet | À remplacer avant publication |

## Musiques

| Fichier | Source | Licence | Date |
| --- | --- | --- | --- |

## Bruitages (CC0 uniquement)

| Fichier | Source | Licence | Date |
| --- | --- | --- | --- |
