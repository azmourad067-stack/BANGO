"""Rapport de la semaine (out/week_<date>/report.html) et copie des épisodes validés dans out/."""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import shutil
from pathlib import Path

from jinja2 import Environment, select_autoescape

from bongo.curriculum import Curriculum, Episode

WATCH_ALL_WEEKS = 3  # semaines 1 à 3 : tout regarder en entier
RANDOM_PICKS = 2


def week_start_for(curriculum: Curriculum, episode: Episode) -> dt.date:
    first = curriculum.episodes[0].date
    return first + dt.timedelta(days=7 * ((episode.date - first).days // 7))


def week_dir(root: Path, start: dt.date) -> Path:
    return root / "out" / f"week_{start.isoformat()}"


def episode_files(folder: Path, episode_id: int) -> dict[str, Path]:
    stem = f"ep{episode_id:03d}"
    return {
        "video": folder / f"{stem}.mp4",
        "srt": folder / f"{stem}.srt",
        "thumb": folder / "thumb.png",
        "metadata": folder / "metadata.json",
    }


def publish_to_week(root: Path, episode_id: int, status: str, target: Path) -> list[str]:
    """Copie les fichiers d'un épisode sans erreur ; retire ceux d'un épisode bloqué. Renvoie les noms copiés."""
    from bongo.pipeline import episode_dir

    stem = f"ep{episode_id:03d}"
    names = {"video": f"{stem}.mp4", "srt": f"{stem}.srt", "thumb": f"{stem}_thumb.png", "metadata": f"{stem}_metadata.json"}
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for key, src in episode_files(episode_dir(root, episode_id), episode_id).items():
        dst = target / names[key]
        if status != "error" and src.is_file():
            shutil.copy2(src, dst)
            copied.append(dst.name)
        else:
            dst.unlink(missing_ok=True)
    return copied


TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Semaine du {{ start }}</title>
<style>
:root{--bg:#f7f5ef;--card:#fff;--ink:#2b2d3a;--muted:#6b6d7a;--ok:#2f8a4c;--warn:#b7791f;--err:#c0392b;--line:#e4e0d6}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{margin:0 0 4px;font-size:1.7rem} .sub{color:var(--muted);margin:0 0 24px}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin:0 0 20px}
.ep{display:grid;grid-template-columns:320px 1fr;gap:20px}
@media(max-width:760px){.ep{grid-template-columns:1fr}}
.ep img{width:100%;border-radius:10px;border:1px solid var(--line)}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:.85rem;font-weight:600}
.b-ok{background:var(--ok)} .b-warning{background:var(--warn)} .b-error{background:var(--err)}
h2{margin:0 0 6px;font-size:1.25rem}
ul.issues{margin:8px 0;padding-left:20px} li.error{color:var(--err)} li.warning{color:var(--warn)}
.field{margin:8px 0} .field b{display:block;font-size:.85rem;color:var(--muted)}
.copy{display:flex;gap:8px;align-items:flex-start}
.copy pre{flex:1;margin:0;white-space:pre-wrap;background:#faf9f5;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font:inherit}
button{cursor:pointer;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 10px;font:inherit}
button:active{background:#eee} a{color:#2563a8}
.watch li{margin:4px 0}
</style></head><body><main>
<h1>Semaine du {{ start }}</h1>
<p class="sub">{{ episodes|length }} épisode(s) — {{ n_ok }} prêt(s), {{ n_warn }} avec avertissement(s), {{ n_err }} bloqué(s). Rapport du {{ generated }}.</p>

<div class="box"><h2>À regarder en entier</h2>
<p>{{ watch_rule }}</p>
<ul class="watch">{% for e in watch %}<li><b>Épisode {{ e.id }}</b> — {{ e.title }} ({{ e.reason }}){% if e.video %} — <a href="{{ e.video }}">ouvrir la vidéo</a>{% endif %}</li>{% endfor %}</ul>
<p>Jette aussi un œil à toutes les miniatures. Au moindre doute, remplace la vidéo par une vidéo de révision.</p></div>

{% for e in episodes %}
<div class="box ep" id="ep{{ e.id }}">
  <div>{% if e.thumb %}<img src="{{ e.thumb }}" alt="Miniature de l'épisode {{ e.id }}">{% endif %}
    <p>{% if e.video %}<a href="{{ e.video }}">Vidéo</a> · <a href="{{ e.srt }}">Sous-titres</a>{% else %}Non copié dans ce dossier (bloqué){% endif %}</p>
    <p class="sub">Durée {{ e.duration }}{% if e.lufs is not none %} · volume {{ e.lufs }} LUFS{% endif %}</p></div>
  <div>
    <h2>Épisode {{ e.id }} — {{ e.date }} <span class="badge b-{{ e.status }}">{{ e.status_fr }}</span></h2>
    {% if e.issues %}<ul class="issues">{% for i in e.issues %}<li class="{{ i.level }}">{{ i.where ~ ' : ' if i.where }}{{ i.message }}</li>{% endfor %}</ul>{% endif %}
    {% if e.meta %}
    {% for label, value in e.fields %}<div class="field"><b>{{ label }}</b><div class="copy"><pre>{{ value }}</pre><button onclick="copyText(this)">Copier</button></div></div>{% endfor %}
    {% endif %}
  </div>
</div>
{% endfor %}
</main>
<script>
function copyText(btn){const t=btn.previousElementSibling.innerText;
 navigator.clipboard.writeText(t).then(()=>{btn.textContent="Copié ✓";setTimeout(()=>btn.textContent="Copier",1500)})}
</script></body></html>
"""


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(path, base).replace(os.sep, "/")


def write_week_report(root: Path, curriculum: Curriculum, start: dt.date) -> Path:
    from bongo.pipeline import episode_dir

    target = week_dir(root, start)
    target.mkdir(parents=True, exist_ok=True)
    week_index = (start - curriculum.episodes[0].date).days // 7
    entries = []
    for ep in curriculum.week(start):
        folder = episode_dir(root, ep.id)
        qa_path = folder / "qa.json"
        if not qa_path.is_file():
            continue
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        meta_path = folder / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else None
        stem = f"ep{ep.id:03d}"
        copied = qa["status"] != "error" and (target / f"{stem}.mp4").is_file()
        thumb = target / f"{stem}_thumb.png" if copied else folder / "thumb.png"
        fields = []
        if meta:
            fields = [
                ("Titre", meta["title"]),
                ("Description", meta["description"]),
                ("Tags", ", ".join(meta["tags"])),
                ("Playlists", " + ".join(meta["playlists"])),
                ("Publication", f"{meta['publish_at_local'][:10]} à {meta['publish_at_local'][11:16]} (heure de Paris)"),
                ("Réglages", "Conçue pour les enfants : Oui · Contenu modifié ou synthétique : Non · "
                             "Langue : anglais (États-Unis) · Catégorie : Éducation"),
            ]
        mins, secs = divmod(int(round(qa.get("duration_s", 0))), 60)
        entries.append({
            "id": ep.id, "date": ep.date.isoformat(), "status": qa["status"],
            "status_fr": {"ok": "ok", "warning": "avertissement", "error": "erreur"}[qa["status"]],
            "title": meta["title"] if meta else ", ".join(ep.new_words),
            "issues": qa.get("issues", []), "meta": meta, "fields": fields,
            "thumb": _rel(thumb, target) if thumb.is_file() else None,
            "video": f"{stem}.mp4" if copied else None, "srt": f"{stem}.srt",
            "duration": f"{mins} min {secs:02d} s", "lufs": qa.get("steps", {}).get("mix", {}).get("integrated_lufs"),
        })

    flagged = [e for e in entries if e["status"] != "ok"]
    if week_index < WATCH_ALL_WEEKS:
        watch = [{**e, "reason": "semaines 1 à 3 : tout regarder"} for e in entries]
        rule = "Semaines 1 à 3 : regarde chaque vidéo en entier."
    else:
        rng = random.Random(start.toordinal())  # graine fixe : tirage reproductible
        ok = [e for e in entries if e["status"] == "ok"]
        picks = rng.sample(ok, min(RANDOM_PICKS, len(ok)))
        watch = [{**e, "reason": "signalé par les contrôles"} for e in flagged]
        watch += [{**e, "reason": "tiré au hasard"} for e in picks]
        rule = "Regarde en entier les vidéos signalées et les 2 tirées au hasard."
    env = Environment(autoescape=select_autoescape(default=True))
    html = env.from_string(TEMPLATE).render(
        start=start.strftime("%d/%m/%Y"), episodes=entries, watch=watch, watch_rule=rule,
        n_ok=sum(e["status"] == "ok" for e in entries), n_warn=sum(e["status"] == "warning" for e in entries),
        n_err=sum(e["status"] == "error" for e in entries),
        generated=dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    path = target / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
