import threading

import numpy as np
import pytest

from jarvis.audio.player import BLOCK_SAMPLES, Player
from jarvis.audio.tts import TTS_SAMPLE_RATE, Speech, WordMark

TEXT = "Ala ma kota. A kot ma Alę."


def speech(text: str, seconds: float, words: list[tuple[str, float, int]]) -> Speech:
    samples = np.full(int(seconds * TTS_SAMPLE_RATE), 0.1, dtype=np.float32)
    return Speech(text, samples, [WordMark(w, s, c) for w, s, c in words])


SEGMENTS = [
    speech("Ala ma kota.", 1.0, [("Ala", 0.0, 3), ("ma", 0.3, 6), ("kota", 0.6, 11)]),
    speech("A kot ma Alę.", 1.0, [("A", 0.0, 1), ("kot", 0.2, 5), ("ma", 0.5, 8), ("Alę", 0.7, 12)]),
]


def drive(player: Player, blocks: int) -> np.ndarray:
    out = np.zeros((BLOCK_SAMPLES, 1), dtype=np.float32)
    for _ in range(blocks):
        player._callback(out, BLOCK_SAMPLES, None, None)
    return out[:, 0].copy()


@pytest.fixture
def player(bus):
    p = Player(bus)
    p._reset()
    p._playing = True
    p._produce(iter(SEGMENTS), TEXT)
    return p


def test_word_positions_across_segments(player, recorder):
    drive(player, int(1.25 * TTS_SAMPLE_RATE / BLOCK_SAMPLES))  # 1,25 s → drugie zdanie, słowo „kot”
    player._publish_progress(0)
    words = recorder.of("tts.word")
    assert [w["text"] for w in words] == ["Ala", "ma", "kota", "A", "kot"]
    assert player.spoken_text(TEXT) == "Ala ma kota. A kot"


def test_duck_ramps_volume_down(player):
    before = drive(player, 5)
    player.duck(0.25)
    drive(player, 5)  # rampa 50 ms = 2,5 bloku
    after = drive(player, 1)
    assert after.max() == pytest.approx(before.max() * 0.25, rel=1e-3)
    assert player.output_level == pytest.approx(0.025, rel=1e-2)
    player.unduck()
    drive(player, 5)
    assert drive(player, 1).max() == pytest.approx(0.1)


def test_stop_fades_out_and_finishes(player):
    drive(player, 5)
    player.stop()
    drive(player, 3)
    assert player._finished.is_set()
    assert drive(player, 1).max() == 0.0


def test_finishes_at_end_of_input(player):
    drive(player, int(2.0 * TTS_SAMPLE_RATE / BLOCK_SAMPLES) + 1)
    assert player._finished.is_set()


class FakeStream:
    """Atrapa sounddevice.OutputStream – wywołuje callback tak szybko, jak się da."""

    def __init__(self, callback, **kwargs):
        self._callback = callback
        self._running = False

    def __enter__(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        out = np.zeros((BLOCK_SAMPLES, 1), dtype=np.float32)
        while self._running:
            self._callback(out, BLOCK_SAMPLES, None, None)

    def __exit__(self, *exc):
        self._running = False
        self._thread.join()


def test_play_full_flow_with_fake_device(bus, recorder, monkeypatch):
    import sounddevice

    monkeypatch.setattr(sounddevice, "OutputStream", FakeStream)
    result = Player(bus).play(iter(SEGMENTS), TEXT)
    assert not result.interrupted and result.spoken == TEXT
    assert len(recorder.of("tts.word")) == 7
    assert recorder.of("audio.level")[-1] == {"source": "tts", "level": 0.0}
