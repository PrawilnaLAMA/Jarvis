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

    opened = 0

    def __init__(self, callback, **kwargs):
        self._callback = callback
        self.active = False
        FakeStream.opened += 1

    def start(self):
        self.active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        out = np.zeros((BLOCK_SAMPLES, 1), dtype=np.float32)
        while self.active:
            self._callback(out, BLOCK_SAMPLES, None, None)

    def stop(self):
        self.active = False
        self._thread.join()

    def close(self):
        pass


def test_play_full_flow_with_fake_device(bus, recorder, monkeypatch):
    import sounddevice

    monkeypatch.setattr(sounddevice, "OutputStream", FakeStream)
    FakeStream.opened = 0
    player = Player(bus)
    try:
        result = player.play(iter(SEGMENTS), TEXT)
        assert not result.interrupted and result.spoken == TEXT
        assert len(recorder.of("tts.word")) == 7
        assert recorder.of("audio.level")[-1] == {"source": "tts", "level": 0.0}
        # kolejna wypowiedź i sygnał korzystają z tego samego, stale otwartego strumienia
        assert player.play(iter(SEGMENTS[:1]), "Ala ma kota.").spoken == "Ala ma kota."
        player.play_effect(np.ones(100, dtype=np.float32))
        assert FakeStream.opened == 1
    finally:
        player.close()


def test_waits_for_start_buffer_so_speech_has_no_gaps(bus):
    player = Player(bus)
    player._reset()
    player._playing = True
    player._min_start_samples = int(1.5 * TTS_SAMPLE_RATE)
    player._buffer = SEGMENTS[0].samples.copy()  # 1 s gotowe, reszta jeszcze się generuje
    assert drive(player, 10).max() == 0.0 and player._pos == 0  # za mały zapas – jeszcze cisza
    player._buffer = np.concatenate([player._buffer, SEGMENTS[1].samples])  # 2 s ≥ 1,5 s
    assert drive(player, 1).max() > 0


def test_short_reply_starts_when_complete(bus):
    player = Player(bus)
    player._reset()
    player._playing = True
    player._min_start_samples = int(5 * TTS_SAMPLE_RATE)
    player._produce(iter(SEGMENTS[:1]), "Ala ma kota.")  # całość gotowa, choć krótsza niż zapas
    assert drive(player, 1).max() > 0


def test_effect_is_mixed_even_when_idle(bus):
    player = Player(bus)
    player._effect = np.full(300, 0.5, dtype=np.float32)
    out = drive(player, 1)
    assert out[:300].max() == pytest.approx(0.5) and out[300:].max() == 0.0
    assert player.output_level == 0.0  # sygnał nie jest „mową” dla filtra echa
