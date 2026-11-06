"""Synchronisation des bouches avec Rhubarb Lip Sync."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from bongo.errors import BongoError
from bongo.schema import BONGO

# Pour les animaux (3 bouches) : X et A → fermée ; B, C, E, F, G, H → mi-ouverte ; D → ouverte
ANIMAL_MOUTHS = {
    "X": "mouth_closed", "A": "mouth_closed",
    "B": "mouth_half", "C": "mouth_half", "E": "mouth_half", "F": "mouth_half", "G": "mouth_half", "H": "mouth_half",
    "D": "mouth_open",
}
RHUBARB_HINT = "Rhubarb Lip Sync est introuvable : suis tools/rhubarb/LISEZMOI.txt puis relance `check-setup`."


def find_rhubarb(root: Path) -> Path:
    from bongo.setup_check import rhubarb_path

    path = rhubarb_path(root)
    if path is None:
        raise BongoError(RHUBARB_HINT)
    return path


def run_rhubarb(rhubarb: Path, wav: Path, txt: Path, out_json: Path) -> list[dict]:
    cmd = [str(rhubarb), "-f", "json", "--extendedShapes", "GHX", "-d", str(txt), str(wav), "-o", str(out_json)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except OSError as exc:
        raise BongoError(f"{RHUBARB_HINT}\nDétail : {exc}") from None
    except subprocess.TimeoutExpired:
        raise BongoError(f"Rhubarb a mis plus de 10 minutes sur {wav.name} : relance la commande.") from None
    if proc.returncode != 0 or not out_json.is_file():
        detail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["?"]
        raise BongoError(f"Rhubarb a échoué sur {wav.name} : {detail[0]}")
    data = json.loads(out_json.read_text(encoding="utf-8"))
    return data.get("mouthCues", [])


def convert_cues(cues: list[dict], speaker: str) -> list[dict]:
    """Formes de Rhubarb pour Bongo (A à H, X) ; 3 bouches pour les animaux."""
    result = []
    for cue in cues:
        shape = cue["value"] if speaker == BONGO else ANIMAL_MOUTHS.get(cue["value"], "mouth_half")
        start, end = round(float(cue["start"]), 3), round(float(cue["end"]), 3)
        if result and result[-1]["shape"] == shape and abs(result[-1]["end"] - start) < 1e-6:
            result[-1]["end"] = end  # fusionne deux formes identiques qui se suivent
        else:
            result.append({"start": start, "end": end, "shape": shape})
    return result


def lipsync_lines(
    lines,
    out_dir: Path,
    rhubarb: Path,
    log: Callable[[str], None] = print,
    runner=run_rhubarb,
) -> dict[str, Path]:
    """Lance Rhubarb sur chaque réplique (en parallèle). Réutilise les résultats déjà à jour."""
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    outputs: dict[str, Path] = {}
    for line in lines:
        target = out_dir / f"{line.id}.json"
        outputs[line.id] = target
        if target.is_file() and target.stat().st_mtime >= max(line.wav.stat().st_mtime, line.txt.stat().st_mtime):
            try:
                if json.loads(target.read_text(encoding="utf-8")).get("speaker") == line.speaker:
                    continue
            except json.JSONDecodeError:
                pass
        todo.append(line)

    def work(line) -> None:
        raw = out_dir / f"{line.id}.rhubarb.json"
        cues = runner(rhubarb, line.wav, line.txt, raw)
        data = {"line_id": line.id, "speaker": line.speaker, "duration_s": line.duration_s,
                "cues": convert_cues(cues, line.speaker)}
        (out_dir / f"{line.id}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        raw.unlink(missing_ok=True)

    if todo:
        log(f"  Rhubarb sur {len(todo)} réplique(s)…")
        workers = max(1, min(len(todo), (os.cpu_count() or 2) - 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))
    return outputs
