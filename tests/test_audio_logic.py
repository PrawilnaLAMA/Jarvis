import numpy as np
import pytest

from jarvis.audio.bargein import DEFAULT_COUPLING, DuckTest, EchoGate, classify_duck
from jarvis.audio.devices import resample, rms, ui_level
from jarvis.audio.recorder import UtteranceRecorder
from jarvis.audio.stt import to_wav, vocabulary_prompt
from jarvis.audio.transcript import clean_transcript, echo_similarity, is_echo, is_hallucination, strip_wake_phrase
from jarvis.audio.tts import Speech, WordMark, locate_words, split_for_speech, trim_silence, voice_entries
from jarvis.settings import Settings

FRAME = np.zeros(1280, dtype=np.int16)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hej Jarvis, puść muzykę.", "puść muzykę."),
        ("hey jarvis która godzina", "która godzina"),
        ("Dżarwis, napisz do Piotrka", "napisz do Piotrka"),
        ("Hej Jarewis! Powiedz coś", "Powiedz coś"),
        ("Hej Żarwis, która godzina", "która godzina"),
        ("Jarvisie, zgaś światło", "zgaś światło"),
        ("Jarzyny są zdrowe", "Jarzyny są zdrowe"),
        ("i wtedy mówię. Hej Jarvis! Dodaj spotkanie", "Dodaj spotkanie"),
        ("Puść muzykę", "Puść muzykę"),
        ("Hej Jarvis.", ""),
    ],
)
def test_strip_wake_phrase(text, expected):
    assert strip_wake_phrase(text) == expected


def test_hallucinations_are_dropped():
    assert is_hallucination("Dziękuję.")
    assert is_hallucination("Napisy stworzone przez społeczność Amara.org")
    assert is_hallucination("Hej Jarvis, Piotrek, Natan.", prompt="Hej Jarvis, Piotrek, Natan.")
    assert not is_hallucination("Dziękuję, to wszystko na dziś, wyłącz muzykę")
    assert clean_transcript("Hej Jarvis. Dzięki za obejrzenie!") == ""
    assert clean_transcript("Hej Jarvis, co mam jutro?") == "co mam jutro?"


def test_echo_detection():
    said = "Rzym został założony w siedemset pięćdziesiątym trzecim roku przed naszą erą przez Romulusa."
    assert is_echo("został założony w siedemset pięćdziesiątym", said)
    assert not is_echo("stop, powiedz mi raczej o Grecji", said)
    assert echo_similarity("", said) == 0.0


def test_echo_gate_learns_coupling_and_ignores_echo():
    gate = EchoGate()
    # Jarvis mówi, mikrofon słyszy echo na poziomie 0.3 × wyjście (VAD też widzi „mowę”)
    for _ in range(20):
        assert not gate.update(mic_level=0.03, vad_prob=0.9, output_level=0.1, noise_floor=0.002)
    assert gate.learned and gate.coupling == pytest.approx(0.3)
    # użytkownik mówi wyraźnie głośniej niż echo przez 3 ramki → kandydat
    assert [gate.update(0.2, 0.9, 0.1, 0.002) for _ in range(3)] == [False, False, True]


def test_echo_gate_needs_learning_before_voice_trigger():
    gate = EchoGate()
    assert not any(gate.update(0.5, 0.99, 0.1, 0.002) for _ in range(5))  # głośno, ale jeszcze nie znamy echa


def test_echo_gate_defaults_and_penalty():
    gate = EchoGate()
    assert gate.coupling == DEFAULT_COUPLING
    gate.outputs.append(0.1)
    before = gate.threshold(0.0)
    gate.penalize()
    assert gate.threshold(0.0) > before


@pytest.mark.parametrize("mic, verdict", [(0.2, "user"), (0.04, "echo"), (0.09, "uncertain")])
def test_classify_duck(mic, verdict):
    assert classify_duck(mic, expected_echo=0.03, noise_floor=0.001) == verdict


def test_duck_test_waits_for_ramp_and_echo_delay():
    test = DuckTest(coupling=0.3, noise_floor=0.001)
    assert [test.add(0.5, 0.015) for _ in range(3)] == [None, None, None]  # pełne echo sprzed ściszenia
    assert test.add(0.004, 0.015) is None
    assert test.add(0.005, 0.015) == "echo"


def test_recorder_waits_for_speech_after_wake_word():
    rec = UtteranceRecorder()
    for _ in range(10):  # pauza po „Hej Jarvis”
        assert not rec.add(FRAME, 0.05)
    for _ in range(10):
        rec.add(FRAME, 0.9)
    assert rec.speech_started
    done_after = [rec.add(FRAME, 0.05) for _ in range(12)]
    assert done_after.index(True) == 9  # 10 × 80 ms = 0,8 s ciszy
    assert rec.has_speech


def test_recorder_ends_despite_quieter_background_speech():
    rec = UtteranceRecorder(speech_started=True)
    for level in (0.06, 0.08, 0.07, 0.09, 0.08):  # użytkownik
        rec.add(FRAME, 0.95, level)
    # telewizor: VAD słyszy mowę, ale ~12 dB ciszej niż użytkownik → to już koniec wypowiedzi
    done = [rec.add(FRAME, 0.9, 0.02) for _ in range(10)]
    assert done[-1] and not any(done[:-1])
    # równie głośna mowa (np. użytkownik mówi dalej) nie kończy nagrania
    rec2 = UtteranceRecorder(speech_started=True)
    for _ in range(20):
        assert not rec2.add(FRAME, 0.9, 0.07)


def test_recorder_times_out_without_speech():
    rec = UtteranceRecorder(start_timeout=0.8)
    assert [rec.add(FRAME, 0.0) for _ in range(10)][-1]
    assert not rec.has_speech


def test_recorder_keeps_preroll_and_limits_length():
    rec = UtteranceRecorder(preroll=[FRAME, FRAME], max_seconds=0.4, speech_started=True)
    while not rec.add(FRAME, 0.9):
        pass
    assert rec.audio().size == 1280 * (2 + 5)


def test_split_for_speech_short_first_chunk():
    text = ("Czy wiesz, że w 2026 roku planowane jest otwarcie pierwszego hotelu pod wodą, gdzie goście będą "
            "mogli spać w przezroczystych pokojach? To ciekawe.")
    chunks = split_for_speech(text)
    assert chunks[0] == "Czy wiesz,"  # pierwszy fragment krótki → szybki pierwszy dźwięk
    assert " ".join(chunks) == text  # nic nie ginie
    for prev, nxt in zip(chunks, chunks[1:], strict=False):  # każdy następny zdąży się wygenerować
        assert len(nxt) <= max(40, 5 * len(prev)) and len(nxt) <= 140
    assert split_for_speech("Otwieram kalendarz.") == ["Otwieram kalendarz."]
    assert split_for_speech("") == []
    # długie zdanie bez przecinka: pierwszy fragment ucięty na granicy słowa
    long = "Aż 75% wszystkich nowych gatunków odkrytych w ostatniej dekadzie pochodzi z głębin oceanów, które są."
    chunks = split_for_speech(long)
    assert chunks[0] == "Aż 75% wszystkich nowych gatunków odkrytych"  # nie „…odkrytych w”
    assert " ".join(chunks) == long
    assert not any(c.rsplit(" ", 1)[-1] in {"w", "z", "że", "na", "do"} for c in chunks)


def test_trim_silence_keeps_word_timing():
    rate = 24000
    samples = np.concatenate([np.zeros(rate // 10), np.full(rate, 0.1), np.zeros(rate // 2)]).astype(np.float32)
    speech = Speech("Ala", samples, [WordMark("Ala", 0.1, 3)])
    trimmed = trim_silence(speech, lead=0.02, tail=0.1)
    assert trimmed.duration == pytest.approx(0.02 + 1.0 + 0.1, abs=0.002)
    assert trimmed.words[0].start == pytest.approx(0.02, abs=0.001)


def test_voice_entries_polish_first_then_multilingual():
    raw = [
        {"ShortName": "en-US-AndrewMultilingualNeural", "Locale": "en-US", "Gender": "Male"},
        {"ShortName": "en-US-GuyNeural", "Locale": "en-US", "Gender": "Male"},
        {"ShortName": "pl-PL-ZofiaNeural", "Locale": "pl-PL", "Gender": "Female"},
        {"ShortName": "de-DE-FlorianMultilingualNeural", "Locale": "de-DE", "Gender": "Male"},
    ]
    assert [(v["name"], v["label"]) for v in voice_entries(raw)] == [
        ("pl-PL-ZofiaNeural", "Zofia"),
        ("en-US-AndrewMultilingualNeural", "Andrew (wielojęzyczny)"),
        ("de-DE-FlorianMultilingualNeural", "Florian (wielojęzyczny)"),
    ]


def test_locate_words_maps_to_text_positions():
    text = "Cześć, jestem Jarvis."
    marks = locate_words(text, [("Cześć", 0.1), ("jestem", 0.9), ("Jarvis", 1.3)])
    assert [m.char_end for m in marks] == [5, 13, 20]
    assert text[: marks[1].char_end] == "Cześć, jestem"


def test_vocabulary_prompt_includes_contacts_and_is_bounded():
    s = Settings.from_dict({
        "contacts": [{"name": "PIOTREK", "channel_id": "1234567", "aliases": ["Piotr"]}],
        "voice": {"vocabulary": ["Wałbrzych"] + [f"słowo{i}" for i in range(200)]},
    })
    prompt = vocabulary_prompt(s)
    assert prompt.startswith("Hej Jarvis, Piotrek, Piotr, Wałbrzych")
    assert len(prompt) <= 601


def test_signal_helpers():
    tone = (np.sin(np.linspace(0, 200, 48000)) * 16000).astype(np.int16)
    assert rms(tone) == pytest.approx(16000 / 32768 / np.sqrt(2), rel=0.02)
    assert resample(tone, 48000, 16000).size == 16000
    assert ui_level(0.0, 0.1) == 0.0 and ui_level(1.0, 0.1) == 1.0
    assert to_wav(FRAME)[:4] == b"RIFF"
