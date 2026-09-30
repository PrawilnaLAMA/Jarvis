"""Krótki dźwięk potwierdzający, że Jarvis usłyszał słowo wywołania (odtwarzany przez Player)."""

import numpy as np

from jarvis.audio.tts import TTS_SAMPLE_RATE


def _tone(freq: float, seconds: float, volume: float) -> np.ndarray:
    t = np.arange(int(TTS_SAMPLE_RATE * seconds)) / TTS_SAMPLE_RATE
    envelope = np.minimum(1.0, np.minimum(t, seconds - t) / 0.01)  # 10 ms narastania i wygaszania
    return (np.sin(2 * np.pi * freq * t) * envelope * volume).astype(np.float32)


CHIME = np.concatenate([_tone(880, 0.07, 0.12), _tone(1320, 0.09, 0.12)])

# przypomnienie z kalendarza: dwa razy wznoszące się trzy tony, głośniej niż CHIME
_REMINDER_ONCE = np.concatenate([_tone(660, 0.1, 0.2), _tone(880, 0.1, 0.2), _tone(1320, 0.16, 0.2)])
REMINDER = np.concatenate([_REMINDER_ONCE, np.zeros(int(TTS_SAMPLE_RATE * 0.12), np.float32), _REMINDER_ONCE])
