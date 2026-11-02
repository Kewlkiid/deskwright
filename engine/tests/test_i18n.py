"""Languages: voice commands, spoken numbers and narrator lines follow the app's language."""
import pytest

from engine import i18n
from engine.config import config
from engine.models.wake import parse_voice


@pytest.fixture
def lang():
    before = config.language

    def use(code):
        config.language = code

    yield use
    config.language = before


@pytest.mark.parametrize("code,said,expected", [
    ("es", "aprobar", ("approve", "")),
    ("es", "Deskwright, para", ("stop", "")),
    ("es", "agente abre el calendario", ("task", "abre el calendario")),
    ("fr", "tais-toi", ("hush", "")),
    ("de", "Deskwright, öffne den Kalender", ("task", "öffne den Kalender")),
    ("pt", "envia", ("send", "")),
    ("es", "approve", ("approve", "")),  # English commands keep working
    ("en", "agents are cool", None),
])
def test_voice_commands_in_each_language(lang, code, said, expected):
    lang(code)
    assert parse_voice(said) == expected


def test_every_language_has_every_line_and_command():
    en = i18n.LANGUAGES["en"]
    for code, info in i18n.LANGUAGES.items():
        assert set(info["lines"]) == set(en["lines"]), code
        assert set(info["commands"]) == set(en["commands"]), code


def test_numbers_spoken_in_the_language(lang):
    from engine.speaker import speakable

    lang("es")
    assert speakable("Son 12 grados") == "Son doce grados"
    lang("en")
    assert speakable("It is 12 degrees") == "It is twelve degrees"


def test_narrator_speaks_the_language(lang):
    from engine.speaker import Narrator

    said = []

    class Spy:
        enabled = True

        def say(self, text, important=False):
            said.append(text)

    lang("fr")
    Narrator(Spy()).on_event("run_finished", {"status": "stopped"})
    Narrator(Spy()).on_event("element_found", {"verb": "click", "target": "Save button at the bottom"})
    assert said == ["Arrêté.", "Je clique"]


def test_planner_told_the_language(lang):
    from engine.models.client import language_line

    lang("en")
    assert language_line() == ""
    lang("de")
    assert "German" in language_line()


@pytest.mark.parametrize("engine,code,pocket_ok,expected", [
    ("pocket", "en", True, "Pocket TTS"),
    ("pocket", "es", True, "Meta MMS-TTS"),  # Pocket speaks English only
    ("mms", "en", True, "Meta MMS-TTS"),  # the default: Meta
    ("pocket", "en", False, "Meta MMS-TTS"),  # not installed: back to Meta
])
def test_which_voice_speaks(monkeypatch, lang, engine, code, pocket_ok, expected):
    import sys
    import types

    from engine.speaker import Speaker

    monkeypatch.setattr(config, "tts_engine", engine)
    lang(code)

    class Fake:
        sample_rate = 24000

        def get_state_for_audio_prompt(self, voice):
            return {}

    class TTSModel:
        @staticmethod
        def load_model():
            if not pocket_ok:
                raise RuntimeError("no weights")
            return Fake()

    monkeypatch.setitem(sys.modules, "pocket_tts", types.SimpleNamespace(TTSModel=TTSModel))

    class Vits:
        @staticmethod
        def from_pretrained(name):
            class M:
                def eval(self):
                    return self

                def __call__(self, **k):
                    return None
            return M()

    class Tok:
        @staticmethod
        def from_pretrained(name):
            return lambda *a, **k: {}

    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(AutoTokenizer=Tok, VitsModel=Vits))
    s = Speaker(lambda *a, **k: None)
    s._lang = code
    s._load()
    assert s.backend == expected
