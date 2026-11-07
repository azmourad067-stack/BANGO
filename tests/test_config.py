import pytest

from bongo.config import PLACEHOLDER, find_root, get_secret, load_config, load_env
from bongo.errors import BongoError


def test_config_values_match_claude_md(config):
    assert (config.video.width, config.video.height, config.video.fps) == (1920, 1080, 24)
    assert config.voices["bongo"].speed == 0.85
    assert config.voices["frog"].speed == 0.90
    assert config.qa.min_word_repeats == 8
    assert config.qa.max_words_per_sentence == 6
    assert config.qa.lesson_duration_s == (200, 260)
    assert config.upload.enabled is False


def test_every_character_has_a_voice(config, curriculum):
    assert all(PLACEHOLDER not in v.voice for v in config.voices.values())
    assert set(curriculum.all_friends()) | {"bongo"} <= set(config.voices)
    assert config.voices["bongo"].voice == "am_liam"  # choisie à l'écoute (novembre 2026)


def test_find_root_from_subfolder(root, monkeypatch):
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    assert find_root(root / "src" / "bongo") == root


def test_find_root_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    with pytest.raises(BongoError, match="config.yaml introuvable"):
        find_root(tmp_path)


def test_bad_config_message(tmp_path):
    (tmp_path / "config.yaml").write_text("video: {width: -1}\n", encoding="utf-8")
    with pytest.raises(BongoError, match="valeur invalide"):
        load_config(tmp_path)


def test_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / ".env").write_text('# commentaire\nGEMINI_API_KEY="abc123"\n', encoding="utf-8")
    assert load_env(tmp_path) == {"GEMINI_API_KEY": "abc123"}
    assert get_secret(tmp_path, "GEMINI_API_KEY") == "abc123"
    assert get_secret(tmp_path, "AUTRE") is None
