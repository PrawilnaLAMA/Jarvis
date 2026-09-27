"""Strumień z mikrofonu: 16 kHz, mono, int16, ramki po 80 ms (tego oczekuje openWakeWord)."""

import contextlib
import logging
import queue

import numpy as np

from jarvis.audio.devices import resample

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms
FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE


class MicStream:
    def __init__(self, device: int | None = None):
        self._device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        self._stream = None
        self._rate = SAMPLE_RATE
        self._pending = np.zeros(0, dtype=np.int16)

    def start(self) -> None:
        import sounddevice as sd

        try:
            self._open(sd, SAMPLE_RATE)
        except sd.PortAudioError:
            # urządzenie nie obsługuje 16 kHz – nagrywamy natywnie i przeliczamy
            rate = int(sd.query_devices(self._device, "input")["default_samplerate"])
            log.info("Mikrofon nie obsługuje 16 kHz, nagrywam w %d Hz", rate)
            self._open(sd, rate)

    def _open(self, sd, rate: int) -> None:
        self._rate = rate
        self._stream = sd.InputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=int(FRAME_SAMPLES * rate / SAMPLE_RATE),
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        block = indata[:, 0].copy()
        if self._rate != SAMPLE_RATE:
            block = resample(block, self._rate, SAMPLE_RATE)
        self._pending = np.concatenate([self._pending, block])
        while self._pending.size >= FRAME_SAMPLES:
            frame, self._pending = self._pending[:FRAME_SAMPLES], self._pending[FRAME_SAMPLES:]
            if self._queue.full():
                with contextlib.suppress(queue.Empty):
                    self._queue.get_nowait()  # przetwarzanie nie nadąża – gubimy najstarszą ramkę
            self._queue.put_nowait(frame)

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("Błąd zamykania mikrofonu")
            self._stream = None
