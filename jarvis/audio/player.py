"""Odtwarzacz mowy z kontrolą w czasie rzeczywistym.

Fragmenty (zdania) mogą dochodzić w trakcie odtwarzania. Odtwarzacz zna dokładną pozycję,
więc wie, które słowa już padły (napisy w UI, kontekst przy przerwaniu), a głośność można
płynnie ściszyć (test echa przy przerywaniu) albo wygasić i zatrzymać.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from jarvis.audio.devices import rms, ui_level
from jarvis.audio.tts import TTS_SAMPLE_RATE, Speech
from jarvis.events import EventBus

log = logging.getLogger(__name__)

BLOCK_SAMPLES = 480  # 20 ms
OUTPUT_LATENCY = 0.1  # bufor karty dźwiękowej (domyślny „high” to 200 ms na Windows)
RAMP_SECONDS = 0.05
UI_UPDATE_SECONDS = 0.033
TTS_LEVEL_REFERENCE = 0.15


@dataclass(frozen=True)
class PlaybackResult:
    interrupted: bool
    spoken: str  # początek tekstu, który zdążył wybrzmieć


@dataclass(frozen=True)
class _Mark:
    sample: int
    char_end: int
    text: str


class Player:
    def __init__(
        self,
        bus: EventBus,
        device: Callable[[], int | None] = lambda: None,
        volume: Callable[[], float] = lambda: 1.0,
    ):
        self._bus = bus
        self._device = device
        self._volume_provider = volume
        self._lock = threading.Lock()
        self._finished = threading.Event()
        self._playing = False
        # strumień wyjściowy jest otwarty cały czas: odpowiedź zaczyna grać od razu, a głośniki
        # USB/Bluetooth nie „zasypiają” i nie ucinają pierwszej sylaby
        self._stream = None
        self._stream_device: int | None = None
        self._effect = np.zeros(0, dtype=np.float32)  # krótkie dźwięki (sygnał „słucham”) miksowane z mową
        self._effect_pos = 0
        self._reset()

    def _reset(self) -> None:
        self._buffer = np.zeros(0, dtype=np.float32)
        self._pos = 0
        self._marks: list[_Mark] = []
        self._input_done = False
        self._stopping = False
        self._gain = 1.0
        self._target = 1.0
        self._volume = 1.0
        self._level = 0.0
        self._spoken_chars = 0
        self._started = False
        self._min_start_samples = 0
        self._gap_samples = 0  # ile ciszy wynikło z czekania na kolejny fragment (diagnostyka)
        self._finished.clear()

    # --- sterowanie (z dowolnego wątku) ---

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def output_level(self) -> float:
        """RMS ostatnio odtworzonego bloku (po uwzględnieniu ściszenia)."""
        return self._level if self._playing else 0.0

    @property
    def is_ducked(self) -> bool:
        return self._playing and self._target < 1.0 and not self._stopping

    def duck(self, gain: float = 0.25) -> None:
        with self._lock:
            if self._playing and not self._stopping:
                self._target = gain

    def unduck(self) -> None:
        with self._lock:
            if self._playing and not self._stopping:
                self._target = 1.0

    def stop(self) -> None:
        with self._lock:
            if self._playing:
                self._stopping = True
                self._target = 0.0

    def spoken_text(self, full_text: str) -> str:
        return full_text[: self._spoken_chars].strip()

    # --- strumień wyjściowy ---

    def _ensure_stream(self) -> bool:
        import sounddevice as sd

        device = self._device()
        if self._stream is not None and self._stream_device == device and self._stream.active:
            return True
        self.close()
        try:
            stream = sd.OutputStream(
                samplerate=TTS_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SAMPLES,
                latency=OUTPUT_LATENCY,
                device=device,
                callback=self._callback,
            )
            stream.start()
        except Exception as e:
            self._bus.notice(f"Nie mogę odtworzyć dźwięku: {e}", "error")
            return False
        self._stream, self._stream_device = stream, device
        return True

    def prepare(self) -> bool:
        """Otwiera wyjście audio zawczasu (przy starcie aplikacji)."""
        return self._ensure_stream()

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.debug("Błąd zamykania strumienia", exc_info=True)
            self._stream = None

    def play_effect(self, samples: np.ndarray) -> None:
        """Krótki dźwięk bez blokowania (miksowany z ewentualną mową)."""
        with self._lock:
            self._effect = samples.astype(np.float32)
            self._effect_pos = 0
        self._ensure_stream()

    # --- odtwarzanie ---

    def play(self, segments: Iterable[Speech], full_text: str, min_start: float = 0.0) -> PlaybackResult:
        """Blokuje do końca odtwarzania albo zatrzymania. `min_start` – ile sekund dźwięku musi być gotowe,
        zanim zacznie grać (zapas na generowanie kolejnych fragmentów, żeby nie było przerw w mowie)."""
        with self._lock:
            self._reset()
            self._volume = self._volume_provider()
            self._min_start_samples = int(min_start * TTS_SAMPLE_RATE)
            self._playing = True
        producer = threading.Thread(target=self._produce, args=(segments, full_text), daemon=True)
        producer.start()
        if not self._ensure_stream():
            with self._lock:
                self._stopping = True
                self._playing = False
            return PlaybackResult(False, full_text)

        started = time.monotonic()
        first_audio_logged = False
        next_mark = 0
        while True:
            done = self._finished.wait(UI_UPDATE_SECONDS)
            next_mark = self._publish_progress(next_mark)
            if not first_audio_logged and self._pos > 0:
                first_audio_logged = True
                log.info("Pierwszy dźwięk po %.0f ms", (time.monotonic() - started) * 1000)
            if done:
                break
            if self._stream is None or not self._stream.active:
                self._bus.notice("Urządzenie audio przestało odpowiadać.", "error")
                break
        with self._lock:
            interrupted = self._stopping
            self._playing = False
        if self._gap_samples:
            log.info("Przerwy w mowie (czekanie na syntezę): %.0f ms", self._gap_samples / TTS_SAMPLE_RATE * 1000)
        self._bus.publish("audio.level", source="tts", level=0.0)
        return PlaybackResult(interrupted, self.spoken_text(full_text) if interrupted else full_text)

    def _produce(self, segments: Iterable[Speech], full_text: str) -> None:
        cursor = 0
        try:
            for segment in segments:
                if self._stopping:
                    break
                idx = full_text.find(segment.text, cursor)
                base = idx if idx >= 0 else cursor
                with self._lock:
                    start = self._buffer.size
                    self._buffer = np.concatenate([self._buffer, segment.samples.astype(np.float32)])
                    self._marks.extend(
                        _Mark(start + int(w.start * TTS_SAMPLE_RATE), base + w.char_end, w.text) for w in segment.words
                    )
                cursor = base + len(segment.text)
        except Exception:
            log.exception("Błąd przygotowania mowy")
        finally:
            with self._lock:
                self._input_done = True

    def _callback(self, outdata, frames, time_info, status) -> None:
        chunk = np.zeros(frames, dtype=np.float32)
        done = False
        with self._lock:
            if self._playing and not self._started:
                ready = self._buffer.size
                self._started = self._input_done or (ready > 0 and ready >= self._min_start_samples)
                if self._stopping and not self._started:
                    done = True
            if self._playing and self._started and not self._finished.is_set():
                available = self._buffer.size - self._pos
                n = min(frames, max(available, 0))
                if n:
                    chunk[:n] = self._buffer[self._pos : self._pos + n]
                    self._pos += n
                if n < frames and not self._input_done and not self._stopping:
                    self._gap_samples += frames - n
                # płynna zmiana głośności (bez trzasków): pełna rampa trwa RAMP_SECONDS
                step = frames / (RAMP_SECONDS * TTS_SAMPLE_RATE)
                end_gain = self._gain + float(np.clip(self._target - self._gain, -step, step))
                chunk *= np.linspace(self._gain, end_gain, frames, dtype=np.float32) * self._volume
                self._gain = end_gain
                done = (self._stopping and self._gain <= 1e-3) or (
                    self._input_done and self._pos >= self._buffer.size
                )
            self._level = rms(chunk)
            if self._effect_pos < self._effect.size:
                n = min(frames, self._effect.size - self._effect_pos)
                chunk[:n] += self._effect[self._effect_pos : self._effect_pos + n]
                self._effect_pos += n
        outdata[:, 0] = chunk
        if done:
            self._finished.set()

    def _publish_progress(self, next_mark: int) -> int:
        with self._lock:
            pos = self._pos
            marks = self._marks[next_mark:]
        for mark in marks:
            if mark.sample > pos:
                break
            self._spoken_chars = mark.char_end
            self._bus.publish("tts.word", index=next_mark, text=mark.text, char_end=mark.char_end)
            next_mark += 1
        self._bus.publish("audio.level", source="tts", level=ui_level(self._level, TTS_LEVEL_REFERENCE))
        return next_mark
