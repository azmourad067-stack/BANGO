import copy
import json
import shutil
from pathlib import Path

import pytest

from bongo.config import load_config
from bongo.curriculum import load_curriculum
from bongo.schema import parse_script
from bongo.script_check import ContentRules, check_script, load_rules

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "content" / "examples" / "ep003_frog_leaf.json"


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def config():
    return load_config(ROOT)


@pytest.fixture(scope="session")
def curriculum():
    return load_curriculum(ROOT)


@pytest.fixture(scope="session")
def rules() -> ContentRules:
    return load_rules(ROOT)


@pytest.fixture
def example() -> dict:
    """Scénario valide de l'épisode 3, à modifier dans chaque test."""
    return copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))


@pytest.fixture
def run_check(config, curriculum, rules):
    def run(data: dict, episode_id: int | None = None, rules_override: ContentRules | None = None):
        script = parse_script(data)
        episode = curriculum.get(episode_id or script.episode_id)
        return check_script(script, episode, curriculum, config, rules_override or rules)

    return run


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Copie minimale du projet (sans assets dessinés) dans un dossier temporaire."""
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    shutil.copytree(ROOT / "content", tmp_path / "content")
    shutil.copytree(ROOT / "assets" / "fonts", tmp_path / "assets" / "fonts")
    shutil.copy(ROOT / "LICENSES.md", tmp_path / "LICENSES.md")
    return tmp_path


def codes(result) -> set[str]:
    return {i.code for i in result.issues}


def find_line(data: dict, text: str) -> dict:
    for scene in data["scenes"]:
        for line in scene["lines"]:
            if line["text"] == text:
                return line
    raise KeyError(text)
