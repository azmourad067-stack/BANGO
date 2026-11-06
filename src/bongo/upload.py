"""Publication automatique sur YouTube — DÉSACTIVÉE (config.yaml : upload.enabled: false).

Une vidéo envoyée par un projet API non audité reste bloquée en privé. Quand l'audit de l'API
YouTube est accepté (voir CLAUDE.md, « Publication automatique ») :
- écran de consentement OAuth en « In production » (sinon le jeton expire au bout de 7 jours) ;
- videos.insert avec privacyStatus: private, publishAt = date du programme, selfDeclaredMadeForKids: true ;
- ne téléverser que les épisodes sans erreur et déjà passés par le rapport.
"""

from __future__ import annotations

from bongo.config import Config
from bongo.errors import BongoError


def ensure_enabled(config: Config) -> None:
    if not config.upload.enabled:
        raise BongoError(
            "La publication automatique est désactivée tant que l'audit de l'API YouTube n'est pas accepté. "
            "Programme les vidéos à la main dans YouTube Studio avec le rapport de la semaine."
        )
    raise BongoError("La publication automatique n'est pas encore programmée : à construire après l'audit.")
