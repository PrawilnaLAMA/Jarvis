"""Krótki dźwięk potwierdzający, że Jarvis usłyszał słowo wywołania (odtwarzany przez Player)."""

import numpy as np

from jarvis.audio.tts import TTS_SAMPLE_RATE


def _tone(freq: float, seconds: float, volume: float) -> np.ndarray:
    t = np.arange(int(TTS_SAMPLE_RATE * seconds)) / TTS_SAMPLE_RATE
    envelope = np.minimum(1.0, np.minimum(t, seconds - t) / 0.01)  # 10 ms narastania i wygaszania
    return (np.sin(2 * np.pi * freq * t) * envelope * volume).astype(np.float32)


CHIME = np.concatenate([_tone(880, 0.07, 0.12), _tone(1320, 0.09, 0.12)])
