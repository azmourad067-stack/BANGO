import json

import pytest

from bongo.config import voice_for
from bongo.errors import BongoError
from bongo.schema import parse_script
from bongo.tts import (
    apply_pronunciations,
    load_pronunciations,
    read_wav,
    synthesize_line,
    synthesize_script,
)
from fakes import FakeSynth


def test_apply_pronunciations():
    prons = {"goodnight": "ɡʊdnˈIt", "leaf": "lˈif"}
    assert apply_pronunciations("Goodnight, leaf! Leafy.", prons) == "[Goodnight](/ɡʊdnˈIt/), [leaf](/lˈif/)! Leafy."
    assert apply_pronunciations("Hello!", {}) == "Hello!"


def test_load_pronunciations(project):
    assert load_pronunciations(project) == {}
    (project / "content" / "pronunciations.yaml").write_text('Frog: "/fɹˈɔɡ/"\n', encoding="utf-8")
    assert load_pronunciations(project) == {"frog": "fɹˈɔɡ"}


def test_variant_splits_sentences():
    synth = FakeSynth()
    one = synthesize_line("Look! A frog!", "am_michael", 0.85, synth, 0)
    two = synthesize_line("Look! A frog!", "am_michael", 0.85, synth, 1)
    assert [c[0] for c in synth.calls] == ["Look! A frog!", "Look!", "A frog!"]
    assert len(two) > len(one) - 1  # silence ajouté entre les phrases


def test_synthesize_script(tmp_path, config, example):
    script = parse_script(example)
    synth = FakeSynth()
    lines = synthesize_script(script, config, tmp_path, synth, {"frog": "fɹˈɔɡ"}, log=lambda m: None)
    assert len(lines) == len(script.all_lines()) == len(synth.calls)
    first = lines[0]
    assert first.id == "l001" and first.scene_id == "s1" and first.speaker == "bongo"
    audio, rate = read_wav(first.wav)
    assert rate == 24_000 and len(audio) > 0
    assert first.txt.read_text(encoding="utf-8").strip() == "Hello, little explorer!"
    # Voix et vitesse depuis config.yaml, prononciation appliquée
    frog_call = next(c for c in synth.calls if c[0].startswith("Hello, Bongo!"))
    assert frog_call[1:] == (config.voices["frog"].voice, 0.90)
    assert any("[Frog](/fɹˈɔɡ/)" in c[0] for c in synth.calls)
    # Deuxième passage : tout est réutilisé
    again = FakeSynth()
    synthesize_script(script, config, tmp_path, again, {"frog": "fɹˈɔɡ"}, log=lambda m: None)
    assert again.calls == []
    # Une variante ne refait que la réplique concernée
    synthesize_script(script, config, tmp_path, again, {"frog": "fɹˈɔɡ"}, {"l002": 1}, log=lambda m: None)
    assert [c[0] for c in again.calls] == ["I am,", "Bongo the gorilla."]


def test_missing_voice(config):
    with pytest.raises(BongoError, match="Aucune voix"):
        voice_for(config, "dragon")
