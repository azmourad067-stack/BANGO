# Bongo the Gorilla — système de production vidéo

Ce dépôt fabrique, par lots d'une semaine, les épisodes de la chaîne YouTube « Bongo the Gorilla » : courtes vidéos d'environ 3 min 50 qui apprennent l'anglais (accent américain) aux enfants de 2 à 4 ans.

La bible de la chaîne (personnage, règles pédagogiques, programme de la saison 1) est la référence pour tout le contenu : https://claude.ai/artifact/7eVh1p6iYRwKVdPLujQFK1

## Contraintes non négociables

- **100 % gratuit.** Aucun service payant, aucun abonnement, aucune clé qui exige une carte bancaire. Avant d'ajouter une dépendance, vérifier que sa licence autorise un usage commercial (la chaîne sera monétisée) et le noter dans `LICENSES.md`.
- **Windows 11.** Le système tourne sur le PC Windows de l'utilisateur. Utiliser `pathlib`, passer les commandes externes à `subprocess` sous forme de listes, ne jamais supposer bash.
- **Autonome.** Une fois construit, le système tourne sans Claude Code : `python -m bongo build-week ...` doit suffire.
- **L'utilisateur n'est pas développeur.** Commandes simples, messages d'erreur en français, qui disent quoi faire (« FFmpeg introuvable : installe-le puis relance `check-setup` »).
- **Le contenu pédagogique ne s'invente pas.** Les mots enseignés, l'ordre et les amis viennent de `content/curriculum.yaml`. Le modèle de langage met en scène, il ne choisit jamais quoi enseigner.
- **Réglages figés.** Les voix, vitesses et dimensions de `config.yaml` ne se modifient pas sans demande explicite de l'utilisateur : la cohérence de Bongo d'un épisode à l'autre en dépend.
- **Reproductible.** Tout l'aléatoire (clignements, choix des épisodes à relire) utilise une graine dérivée du numéro d'épisode.
- **Aucune donnée personnelle** dans les requêtes envoyées à l'API Gemini : son palier gratuit peut servir à améliorer les produits Google.

## Outils

| Rôle | Outil | Licence | Remarque |
| --- | --- | --- | --- |
| Langage | Python 3.11 ou 3.12 | — | Vérifier la version supportée par Kokoro avant de choisir |
| Scénarios | API Gemini, palier gratuit, SDK `google-genai` | — | Clé dans `.env` (`GEMINI_API_KEY`) ; nom du modèle dans `config.yaml` (un modèle Flash gratuit, à vérifier dans Google AI Studio) |
| Voix | Kokoro (`kokoro`, `soundfile`) | Apache 2.0 | Anglais américain ; suivre le README pour l'installation Windows (espeak-ng) |
| Contrôle de prononciation | `faster-whisper`, modèle `small.en`, CPU, int8 | MIT | Transcrit chaque réplique pour vérifier qu'elle est bien prononcée |
| Synchronisation des bouches | Rhubarb Lip Sync (binaire Windows) | Vérifier le fichier de licence du dépôt | Placé dans `tools/rhubarb/` |
| Image | Pillow, numpy | HPND, BSD | Assemblage des calques |
| Vidéo et audio | FFmpeg (build Windows dans le PATH) | LGPL/GPL | Encodage H.264 `-preset veryfast -crf 20`, AAC 192k |
| Divers | PyYAML, pydantic, jinja2, pytest | MIT/BSD | Configuration, validation, rapport HTML, tests |
| Police | Fredoka ou équivalent sous licence OFL | OFL | Cartes-mots et miniatures ; fichier de licence dans `assets/fonts/` |

## Arborescence

```
bongo/
  CLAUDE.md
  LICENSES.md                 # une ligne par dépendance, asset, musique, bruitage
  config.yaml
  .env                        # GEMINI_API_KEY — jamais versionné
  content/
    curriculum.yaml           # programme de la saison (voir plus bas)
    allowed_words.txt         # petits mots courants autorisés (I, you, look, the, a, is, can, say, yes, wow…)
    banned_words.txt          # mots interdits (scary, monster, hurt, dead…)
    pronunciations.yaml       # corrections phonétiques validées à l'écoute
    quest_history.yaml        # résumé des quêtes déjà utilisées (pour varier les histoires)
  assets/
    characters/bongo/body/{stand,arms_up,drum_a,drum_b,point,crouch,sleep}.png
    characters/bongo/eyes/{open,half,closed,left,right}.png
    characters/bongo/brows/{neutral,surprised}.png
    characters/bongo/mouth/{A,B,C,D,E,F,G,H,X}.png
    characters/bongo/rig.json         # points d'ancrage (cou, yeux, bouche, pieds)
    characters/<animal>/{pose_1,pose_2,eyes_open,eyes_closed,mouth_closed,mouth_half,mouth_open}.png + rig.json
    backgrounds/<milieu>/<décor>.png  # 2560x1440 pour permettre les panoramiques
    cards/<mot>.png                   # image de la carte-mot
    audio/music/  audio/sfx/  audio/chants/
    fonts/
  src/bongo/
    cli.py  config.py  curriculum.py  schema.py
    script_gen.py  script_check.py
    tts.py  asr_check.py  lipsync.py
    timeline.py  render.py  audio_mix.py
    subtitles.py  thumbnail.py  metadata.py
    compile.py  report.py  placeholders.py
    upload.py                 # désactivé tant que l'audit de l'API YouTube n'est pas accepté
  episodes/ep003/             # script.json, audio/, lipsync/, timeline.json, qa.json, ep003.mp4, ep003.srt, thumb.png, metadata.json
  out/week_2026-12-01/        # vidéos validées + report.html
  tests/
```

## Formats de données

### `content/curriculum.yaml`

```yaml
season: 1
episodes:
  - id: 3
    date: 2026-12-03
    type: lesson            # lesson | review
    biome: jungle
    backgrounds: [nest, clearing]
    new_words: [frog, leaf]
    review_words: [parrot]
    friends: [frog]
    action: jump            # geste à mimer
  - id: 7
    date: 2026-12-07
    type: review
    biome: jungle
    backgrounds: [nest, big_tree]
    review_words: [hello, gorilla, parrot, tree, frog, leaf, elephant, big, banana, small, flower, friend]
    friends: [parrot, frog, elephant]
```

Le programme complet des 28 épisodes est dans la bible ; le recopier ici à l'identique.

### `episodes/epNNN/script.json` (validé par un modèle pydantic dans `schema.py`)

```json
{
  "episode_id": 3,
  "title": "Frog and Leaf",
  "quest_summary": "Frog lost his favorite leaf and Bongo helps him find it.",
  "scenes": [
    {
      "id": "s1",
      "segment": "hello",
      "background": "nest",
      "characters": [{"name": "bongo", "pose": "stand", "position": "center"}],
      "lines": [
        {"speaker": "bongo", "text": "Hello, little explorer!", "pose": "arms_up"},
        {"speaker": "bongo", "text": "Can you say frog?", "prompt_word": "frog", "pause_after": 3.0},
        {"speaker": "bongo", "text": "Frog! Great job!", "card": "frog"}
      ]
    }
  ]
}
```

Segments autorisés, dans cet ordre : `hello`, `quest`, `encounter_1`, `encounter_2`, `review_word`, `success`, `recap`, `goodbye`. Un épisode de révision utilise `hello`, `recap` (plusieurs scènes, une par ami) et `goodbye`.

## Chaîne de fabrication d'un épisode

1. **`script_gen`** — Envoie à Gemini : les règles de la bible (résumées dans le prompt système), l'entrée du programme, la liste des mots autorisés et `quest_history.yaml`. Demande une réponse JSON conforme au schéma (`response_mime_type: application/json`). Si la validation ou les contrôles échouent, renvoie les erreurs au modèle, 3 essais au maximum. En cas de quota dépassé : arrêt propre avec message clair, jamais de script non contrôlé. Option `--script-file chemin.json` : utiliser un script écrit à la main, qui passe par les mêmes contrôles.
2. **`script_check`** — Bloque l'épisode (`error`) si :
   - un mot nouveau est entendu moins de 8 fois (toutes répliques confondues, sans tenir compte de la casse ; le pluriel en -s compte) ;
   - un mot nouveau a moins de 2 cartes-mots ;
   - une réplique `prompt_word` a une pause inférieure à 3 s, ou n'est pas suivie d'une réplique de Bongo qui redit le mot ;
   - une phrase de Bongo dépasse 6 mots ;
   - un mot n'est ni dans `allowed_words.txt`, ni dans les mots du programme vus jusqu'ici, ni un nom d'ami, ni « Bongo » ;
   - un mot de `banned_words.txt` apparaît ;
   - la durée estimée sort de l'intervalle de `config.yaml` ;
   - la quête ressemble trop à une quête de `quest_history.yaml`.

   Avertissement (`warning`) seulement : aucun geste à mimer, mot rappelé absent.
3. **`tts`** — Une réplique = un fichier WAV 24 kHz. Voix et vitesse par personnage depuis `config.yaml`. Applique `pronunciations.yaml` avec le mécanisme de phonèmes personnalisés de Kokoro (vérifier la syntaxe dans la documentation de la version installée).
4. **`asr_check`** — faster-whisper transcrit chaque WAV. Erreur si un mot cible n'est pas reconnu à l'identique ; avertissement si l'écart sur le reste de la phrase dépasse 20 %. Une réplique en erreur est régénérée une fois, puis signalée.
5. **`lipsync`** — Rhubarb pour chaque réplique : `rhubarb -f json --extendedShapes GHX -d replique.txt replique.wav -o replique.json` (le texte fourni avec `-d` améliore la précision). Pour les animaux, convertir les formes en 3 bouches : X et A → fermée ; B, C, E, F, G, H → mi-ouverte ; D → ouverte.
6. **`timeline`** — Calcule `timeline.json` : début et fin de chaque réplique (répliques bout à bout + `pause_after` + 0,4 s entre deux répliques), poses, clignements toutes les 2,5 à 5 s, cartes-mots (2,5 s à l'écran, apparition en 0,3 s), léger zoom lent du décor (2 à 4 % par scène), fondu de 0,5 s entre les scènes, aucun plan de moins de 3 s.
7. **`render`** — Assemble les calques avec Pillow en 1920x1080, 24 images/s, et envoie les images brutes à FFmpeg par un tube (`-f rawvideo -pix_fmt rgb24` → `libx264 -preset veryfast -crf 20 -pix_fmt yuv420p`). Met les calques en cache. Respiration au repos : le corps grandit de 1 % puis revient, sur 3 s. Positions `left`, `center` et `right` définies dans `config.yaml`. Pas de clignotement, pas de mouvement brusque.
8. **`audio_mix`** — Place les répliques selon la timeline, ajoute la musique de fond (20 dB sous la voix, coupée pendant les pauses où l'enfant répond) et les bruitages, normalise avec `loudnorm` (I=-14, TP=-1.5), puis assemble avec la vidéo.
9. **`subtitles`** — Génère le fichier `.srt` à partir de la timeline.
10. **`thumbnail`** — Miniature 1280x720 : décor, Bongo bras levés, l'ami du jour, les mots du jour en gros caractères.
11. **`metadata`** — `metadata.json` : titre (« Frog and Leaf — Learn English with Bongo the Gorilla »), description courte et descriptive, une liste réduite de mots-clés, playlist du milieu, date et heure de publication (13:00, Europe/Paris), « conçu pour les enfants » = oui. Jamais de bourrage de mots-clés.
12. **`report`** — `out/week_<date>/report.html` : pour chaque épisode, la miniature, le statut des contrôles (ok / avertissement / erreur), le détail des alertes, les métadonnées à copier dans YouTube Studio, et 2 épisodes tirés au hasard (graine fixe) à regarder en entier. Seuls les épisodes sans erreur sont copiés dans `out/`.

## Compilations

`python -m bongo compile --from 1 --to 7 --title "Bongo's Week in the Jungle"` : carton d'introduction rendu par le même moteur, puis les épisodes bout à bout (démultiplexeur concat de FFmpeg), avec miniature, sous-titres et métadonnées propres.

## Commandes

| Commande | Rôle |
| --- | --- |
| `python -m bongo check-setup` | Vérifie Python, FFmpeg, Rhubarb, Kokoro, le modèle Whisper, la clé Gemini et les assets de chaque milieu |
| `python -m bongo placeholders` | Génère des assets provisoires (formes simples) pour développer sans attendre les dessins |
| `python -m bongo voices --text "Hello, little explorer!"` | Fait dire la phrase par toutes les voix américaines de Kokoro, pour choisir à l'écoute |
| `python -m bongo pronounce` | Fait dire chaque mot du programme par la voix de Bongo, pour l'écoute unique de contrôle |
| `python -m bongo build-episode 3` | Fabrique un épisode |
| `python -m bongo build-week --start 2026-12-01` | Fabrique les 7 épisodes d'une semaine et le rapport |
| `python -m bongo compile --from 1 --to 7 --title "..."` | Fabrique une compilation |

## `config.yaml` (valeurs de départ)

```yaml
video: {width: 1920, height: 1080, fps: 24}
positions: {left: 0.25, center: 0.5, right: 0.75}   # fraction de la largeur
voices:
  bongo:    {voice: "A_CHOISIR", speed: 0.85}
  parrot:   {voice: "A_CHOISIR", speed: 0.90}
  frog:     {voice: "A_CHOISIR", speed: 0.90}
  elephant: {voice: "A_CHOISIR", speed: 0.90}
llm: {model: "A_CHOISIR_MODELE_FLASH_GRATUIT", temperature: 0.7, max_retries: 3}
qa:
  min_word_repeats: 8
  min_cards_per_word: 2
  max_words_per_sentence: 6
  prompt_pause_s: 3.0
  lesson_duration_s: [200, 260]
  review_duration_s: [300, 360]
  min_shot_s: 3
audio: {music_db_under_voice: -20, loudness_lufs: -14}
publish: {time: "13:00", timezone: "Europe/Paris"}
upload: {enabled: false}
```

## Ordre de construction

| Étape | Dates cibles | Livrable |
| --- | --- | --- |
| 1 | 10–12 nov. | `check-setup`, `placeholders`, `voices`, chargement du programme, schéma du script et `script_check` avec leurs tests |
| 2 | 12–15 nov. | `script_gen`, `tts`, `asr_check`, `lipsync` : un épisode en audio seul |
| 3 | 15–20 nov. | `timeline` et `render` avec les assets provisoires, puis avec les vrais dessins |
| 4 | 20–24 nov. | `audio_mix`, `subtitles`, `thumbnail`, `metadata`, `report` : un épisode pilote complet |
| 5 | 24–28 nov. | `build-week`, `compile`, robustesse : production de la semaine 1 |

Après chaque étape : tests au vert, une commande que l'utilisateur peut lancer lui-même, et un court résumé en français de ce qui marche et de ce qui reste.

## Publication automatique (plus tard)

`upload.py` reste désactivé (`upload.enabled: false`). Une vidéo envoyée par un projet API non audité reste bloquée en privé. Quand l'audit de l'API YouTube est accepté :

- passer l'écran de consentement OAuth en « In production » (sinon le jeton expire au bout de 7 jours) ;
- envoyer avec `videos.insert` : `privacyStatus: private`, `publishAt` à la date du programme, `selfDeclaredMadeForKids: true` ;
- ne téléverser que les épisodes sans erreur et déjà passés par le rapport.

## Sécurité

- `.env`, les jetons OAuth et `episodes/` sont dans `.gitignore`.
- Si le projet va sur GitHub : dépôt **privé** (les dessins de Bongo ne doivent pas être publics).
