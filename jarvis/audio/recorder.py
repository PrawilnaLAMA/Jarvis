"""Nagrywanie jednej wypowiedzi: od słowa wywołania do chwili ciszy."""

from dataclasses import dataclass, field

import numpy as np

from jarvis.audio.mic import FRAME_SECONDS

SPEECH_ON = 0.5
SPEECH_OFF = 0.3


@dataclass
class UtteranceRecorder:
    preroll: list[np.ndarray] = field(default_factory=list)
    silence_seconds: float = 0.9  # tyle ciszy kończy wypowiedź
    start_timeout: float = 5.0  # tyle czekamy, aż użytkownik zacznie mówić
    max_seconds: float = 15.0
    frames: list[np.ndarray] = field(default_factory=list)
    speech_started: bool = False
    speech_frames: int = 0
    done: bool = False
    _recent: list[float] = field(default_factory=list)
    _silence: int = 0
    _elapsed: int = 0

    def add(self, frame: np.ndarray, vad_prob: float) -> bool:
        """Dodaje ramkę; zwraca True, gdy wypowiedź się skończyła."""
        if self.done:
            return True
        self.frames.append(frame)
        self._elapsed += 1
        self._recent = (self._recent + [vad_prob])[-3:]
        elapsed = self._elapsed * FRAME_SECONDS

        if vad_prob >= SPEECH_ON:
            self.speech_frames += 1
        if not self.speech_started:
            # początek mowy: 2 z 3 ostatnich ramek z mową (odporne na pojedyncze trzaski)
            if sum(p >= SPEECH_ON for p in self._recent) >= 2:
                self.speech_started = True
            elif elapsed >= self.start_timeout:
                self.done = True
        else:
            self._silence = self._silence + 1 if vad_prob < SPEECH_OFF else 0
            if self._silence * FRAME_SECONDS >= self.silence_seconds:
                self.done = True
        if elapsed >= self.max_seconds:
            self.done = True
        return self.done

    @property
    def has_speech(self) -> bool:
        return self.speech_started and self.speech_frames >= 3

    def audio(self) -> np.ndarray:
        return np.concatenate(self.preroll + self.frames) if (self.preroll or self.frames) else np.zeros(0, np.int16)
