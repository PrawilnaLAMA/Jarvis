"""Krótki dźwięk potwierdzający, że Jarvis usłyszał słowo wywołania."""

import logging

import numpy as np

log = logging.getLogger(__name__)

_RATE = 24000


def _tone(freq: float, seconds: float, volume: float) -> np.ndarray:
    t = np.arange(int(_RATE * seconds)) / _RATE
    envelope = np.minimum(1.0, np.minimum(t, seconds - t) / 0.01)  # 10 ms narastania i wygaszania
    return (np.sin(2 * np.pi * freq * t) * envelope * volume).astype(np.float32)


CHIME = np.concatenate([_tone(880, 0.07, 0.12), _tone(1320, 0.09, 0.12)])


def play_chime(device: int | None = None) -> None:
    try:
        import sounddevice as sd

        sd.play(CHIME, _RATE, device=device)
    except Exception:
        log.exception("Nie udało się odtworzyć sygnału")
