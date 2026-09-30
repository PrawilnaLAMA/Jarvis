import numpy as np
import pytest

from jarvis.audio.speaker import SpeechResult
from jarvis.audio.voice_loop import BargeIn, VoiceLoop
from jarvis.settings import SettingsStore
from jarvis.state import StatusTracker


def frame(level: float) -> np.ndarray:
    """Ramka o zadanym poziomie RMS (sygnał stały)."""
    return np.full(1280, int(level * 32768), dtype=np.int16)


SILENCE = frame(0.0)


class FakeWake:
    def __init__(self):
        self.next_score = 0.0
        self.resets = 0

    def score(self, f):
        score, self.next_score = self.next_score, 0.0
        return score

    def reset(self):
        self.resets += 1


class FakeVAD:
    """Mowa = każdy sygnał powyżej progu."""

    def probability(self, f):
        return 0.9 if np.abs(f).mean() / 32768 > 0.005 else 0.0


class FakeSTT:
    def __init__(self):
        self.text = ""
        self.calls = 0

    def transcribe(self, pcm):
        self.calls += 1
        return self.text


class FakeSpeaker:
    def __init__(self):
        self.is_speaking = False
        self.current_text = "Rzym został założony w siedemset pięćdziesiątym trzecim roku przed naszą erą."
        self.current_kind = "reply"
        self.stopped = 0
        self.on_end = None

    def spoken_so_far(self):
        return "Rzym został założony"

    def stop(self):
        self.stopped += 1
        self.is_speaking = False


class FakePlayer:
    def __init__(self):
        self.base_level = 0.0
        self.gain = 1.0
        self.calls = []

    @property
    def output_level(self):
        return self.base_level * self.gain

    @output_level.setter
    def output_level(self, value):
        self.base_level = value

    def duck(self, gain):
        self.gain = gain
        self.calls.append(("duck", gain))

    def unduck(self):
        self.gain = 1.0
        self.calls.append(("unduck",))


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path, bus, recorder):
    settings = SettingsStore(tmp_path / "settings.json")
    parts = {
        "wake": FakeWake(), "stt": FakeSTT(), "speaker": FakeSpeaker(), "player": FakePlayer(), "clock": Clock(),
        "responses": [], "chimes": [],
    }
    loop = VoiceLoop(
        mic=None, wake=parts["wake"], vad=FakeVAD(), stt=parts["stt"], speaker=parts["speaker"],
        player=parts["player"], tracker=StatusTracker(bus), settings=settings, bus=bus,
        respond=lambda text, barge: parts["responses"].append((text, barge)),
        chime=lambda: parts["chimes"].append(1), clock=parts["clock"],
    )
    parts["loop"] = loop
    parts["settings"] = settings
    return parts


def feed(loop, level, n):
    for _ in range(n):
        loop.process_frame(frame(level))


def run_job(loop):
    job = loop._jobs.get_nowait()
    loop.process_job(job)
    with loop._pending_lock:
        loop._pending -= 1
    return job


def test_wake_word_pause_then_command(env, recorder):
    loop, wake, stt = env["loop"], env["wake"], env["stt"]
    feed(loop, 0.0, 3)
    wake.next_score = 0.95
    loop.process_frame(frame(0.05))  # koniec „Hej Jarvis”
    assert env["chimes"] == [1] and wake.resets == 1
    feed(loop, 0.0, 15)  # pauza przed poleceniem nie kończy nagrania
    assert loop._recorder is not None
    feed(loop, 0.05, 10)  # polecenie
    feed(loop, 0.0, 12)  # cisza kończy nagranie
    assert loop._recorder is None and loop._busy
    stt.text = "Hej Jarvis, która godzina?"
    job = run_job(loop)
    assert job.barge_in is None and not job.require_wake
    assert env["responses"] == [("która godzina?", None)]
    assert "listening" in [e["state"] for e in recorder.of("state")]


def test_only_wake_phrase_gives_no_response(env):
    loop, wake, stt = env["loop"], env["wake"], env["stt"]
    wake.next_score = 0.95
    loop.process_frame(frame(0.05))
    feed(loop, 0.05, 5)
    feed(loop, 0.0, 12)
    stt.text = "Hej Jarvis."
    run_job(loop)
    assert env["responses"] == []


def test_below_threshold_or_during_cooldown_is_ignored(env):
    loop, wake, clock = env["loop"], env["wake"], env["clock"]
    wake.next_score = 0.3
    loop.process_frame(SILENCE)
    assert loop._recorder is None
    wake.next_score = 0.9
    loop.process_frame(SILENCE)
    loop._recorder = None  # porzucamy nagranie
    wake.next_score = 0.9
    loop.process_frame(SILENCE)  # w czasie blokady (2 s) nie reagujemy ponownie
    assert loop._recorder is None
    clock.now += 3
    wake.next_score = 0.9
    loop.process_frame(SILENCE)
    assert loop._recorder is not None


def start_speaking(env, echo_level=0.03, output=0.1, frames=20):
    """Jarvis mówi; mikrofon słyszy echo (coupling 0.3)."""
    env["speaker"].is_speaking = True
    env["player"].output_level = output
    feed(env["loop"], echo_level, frames)
    assert env["player"].calls == []  # samo echo nie przerywa


def interrupt(env, level_after_duck):
    """Użytkownik zaczyna mówić (3 ramki → ściszenie), potem 5 ramek testu ściszenia."""
    loop, player = env["loop"], env["player"]
    feed(loop, 0.2, 3)
    assert player.calls == [("duck", 0.15)]
    feed(loop, level_after_duck, 5)


def test_barge_in_by_voice_stops_jarvis_and_passes_context(env):
    loop, speaker, stt = env["loop"], env["speaker"], env["stt"]
    start_speaking(env)
    interrupt(env, 0.2)  # po ściszeniu Jarvisa w mikrofonie wciąż głośno → to człowiek
    assert speaker.stopped == 1
    feed(loop, 0.05, 5)
    feed(loop, 0.0, 12)
    stt.text = "Stop, powiedz mi raczej o Grecji."
    job = run_job(loop)
    expected = BargeIn("Rzym został założony", "reply", speaker.current_text)
    assert job.barge_in == expected
    assert env["responses"] == [("Stop, powiedz mi raczej o Grecji.", expected)]


def test_barge_in_transcript_that_is_echo_gets_no_answer(env):
    loop, stt = env["loop"], env["stt"]
    start_speaking(env)
    interrupt(env, 0.2)
    feed(loop, 0.0, 12)
    stt.text = "w siedemset pięćdziesiątym trzecim roku"  # Jarvis usłyszał sam siebie
    run_job(loop)
    assert env["responses"] == []


def test_duck_test_recognizes_echo(env):
    loop, speaker, player = env["loop"], env["speaker"], env["player"]
    start_speaking(env)
    margin = loop._gate.margin
    interrupt(env, 0.004)  # po ściszeniu zostało tyle, ile echa ze ściszonego Jarvisa
    assert player.calls == [("duck", 0.15), ("unduck",)]
    assert speaker.stopped == 0 and loop._recorder is None
    assert loop._gate.margin > margin


def test_uncertain_duck_test_keeps_talking(env):
    loop, speaker, player = env["loop"], env["speaker"], env["player"]
    start_speaking(env)
    margin = loop._gate.margin
    interrupt(env, 0.014)  # pomiędzy – nie ryzykujemy przerwania
    assert player.calls[-1] == ("unduck",)
    assert speaker.stopped == 0 and loop._recorder is None
    assert loop._gate.margin == margin


def test_wakeword_mode_ignores_plain_speech(env):
    loop, speaker, wake, settings = env["loop"], env["speaker"], env["wake"], env["settings"]
    settings.update({"voice": {"barge_in": "wakeword"}})
    loop._cfg = settings.get()
    start_speaking(env)
    feed(loop, 0.2, 10)
    assert speaker.stopped == 0
    wake.next_score = 0.9
    loop.process_frame(frame(0.2))
    assert speaker.stopped == 1 and loop._recorder is not None


def test_follow_up_without_wake_word(env, recorder):
    loop, speaker, clock = env["loop"], env["speaker"], env["clock"]
    speaker.on_end(SpeechResult("Odpowiedź", "reply", False, "Odpowiedź"))
    loop.process_frame(SILENCE)
    assert recorder.of("state")[-1]["state"] == "follow_up"
    feed(loop, 0.05, 2)
    assert loop._recorder is not None and env["chimes"] == []

    loop._recorder = None
    clock.now += 10  # po oknie follow-up mowa bez „Hej Jarvis” jest ignorowana
    feed(loop, 0.05, 5)
    assert loop._recorder is None
    assert recorder.of("state")[-1]["state"] == "idle"


def test_question_waits_longer_even_with_follow_up_off(env):
    loop, speaker, clock, settings = env["loop"], env["speaker"], env["clock"], env["settings"]
    settings.update({"voice": {"follow_up_seconds": 0}})
    loop._cfg = settings.get()
    speaker.on_end(SpeechResult("Dodałem.", "reply", False, "Dodałem."))
    feed(loop, 0.05, 5)
    assert loop._recorder is None  # zwykła odpowiedź – bez follow-upu

    speaker.on_end(SpeechResult("Ile wcześniej mam ci przypomnieć?", "reply", False, ""))
    clock.now += 8  # dłużej niż domyślne 5 s
    feed(loop, 0.05, 2)
    assert loop._recorder is not None and env["chimes"] == []


def test_interrupted_speech_does_not_open_follow_up(env):
    loop, speaker = env["loop"], env["speaker"]
    speaker.on_end(SpeechResult("x", "reply", True, ""))
    feed(loop, 0.05, 5)
    assert loop._recorder is None


def test_mute_ignores_everything_and_trigger_unmutes(env, recorder):
    loop, wake = env["loop"], env["wake"]
    loop.set_muted(True)
    wake.next_score = 0.99
    loop.process_frame(frame(0.1))
    assert loop._recorder is None
    assert recorder.of("state")[-1]["state"] == "muted"
    loop.trigger()
    assert not loop.muted
    loop.process_frame(SILENCE)
    assert loop._recorder is not None and env["chimes"] == [1]


def soft_wake_recording(env, text):
    loop, wake, stt = env["loop"], env["wake"], env["stt"]
    wake.next_score = 0.3  # poniżej progu 0,5, ale powyżej 0,5 × 0,4
    loop.process_frame(frame(0.05))
    feed(loop, 0.05, 3)  # okno oczekiwania na pełne wykrycie
    assert loop._recorder is not None and loop._record_mode == "tentative"
    assert env["chimes"] == []  # bez sygnału – jeszcze nie wiemy, czy to do nas
    feed(loop, 0.05, 5)
    feed(loop, 0.0, 12)
    stt.text = text
    return run_job(loop)


def test_soft_wake_verified_by_transcript(env):
    job = soft_wake_recording(env, "Hej Jarvis, która jest godzina?")
    assert job.require_wake
    assert env["responses"] == [("która jest godzina?", None)]


def test_soft_wake_without_wake_phrase_is_ignored(env):
    soft_wake_recording(env, "która jest godzina?")
    assert env["responses"] == []


def test_soft_wake_with_only_wake_phrase_starts_listening(env):
    loop = env["loop"]
    soft_wake_recording(env, "Hej Jarvis.")
    assert env["responses"] == []
    loop.process_frame(SILENCE)
    assert loop._recorder is not None and loop._record_mode == "command" and env["chimes"] == [1]


def test_soft_then_full_wake_is_normal_command(env):
    loop, wake = env["loop"], env["wake"]
    wake.next_score = 0.3
    loop.process_frame(frame(0.05))
    wake.next_score = 0.9
    loop.process_frame(frame(0.05))
    assert loop._record_mode == "command" and env["chimes"] == [1]


def test_busy_loop_ignores_wake_word(env):
    loop, wake = env["loop"], env["wake"]
    loop._pending = 1  # trwa myślenie
    wake.next_score = 0.99
    loop.process_frame(frame(0.1))
    assert loop._recorder is None
