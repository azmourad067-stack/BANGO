import json

from PIL import Image

from bongo.assets import missing_assets_for_biome
from bongo.curriculum import load_curriculum
from bongo.placeholders import count_placeholders_in_use, generate_placeholders
from bongo.schema import BONGO_POSES


def test_generate_all_assets(project):
    curriculum = load_curriculum(project)
    for biome in ("jungle", "forest", "river", "mountain"):
        assert missing_assets_for_biome(project, curriculum, biome)
    stats = generate_placeholders(project, curriculum)
    assert stats["created"] > 100
    for biome in ("jungle", "forest", "river", "mountain"):
        assert missing_assets_for_biome(project, curriculum, biome) == []
    bg = Image.open(project / "assets/backgrounds/jungle/clearing.png")
    assert bg.size == (2560, 1440)
    assert (project / "assets/backgrounds/common/nest.png").is_file()
    body = Image.open(project / "assets/characters/bongo/body/stand.png")
    assert body.mode == "RGBA"
    rig = json.loads((project / "assets/characters/bongo/rig.json").read_text())
    assert set(rig["face"]) == set(BONGO_POSES)
    assert count_placeholders_in_use(project) == stats["created"]


def test_real_drawings_never_overwritten(project):
    curriculum = load_curriculum(project)
    generate_placeholders(project, curriculum)
    real = project / "assets/characters/bongo/body/stand.png"
    Image.new("RGBA", (10, 10), (255, 0, 0, 255)).save(real)
    before = real.read_bytes()
    stats = generate_placeholders(project, curriculum, force=True)
    assert real.read_bytes() == before
    assert stats["replaced"] > 0
    # Le vrai dessin ne compte plus parmi les provisoires
    manifest = (project / "assets/placeholders.txt").read_text()
    assert "assets/characters/bongo/body/stand.png" not in manifest


def test_second_run_keeps_files(project):
    curriculum = load_curriculum(project)
    generate_placeholders(project, curriculum)
    stats = generate_placeholders(project, curriculum)
    assert stats["created"] == 0 and stats["replaced"] == 0
