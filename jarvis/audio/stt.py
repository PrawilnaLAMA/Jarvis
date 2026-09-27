"""Rozpoznawanie mowy przez Whisper (Groq)."""

import io
import logging
import wave
from collections.abc import Callable

import numpy as np
import requests

from jarvis.audio.mic import SAMPLE_RATE
from jarvis.settings import Settings

log = logging.getLogger(__name__)

TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_PROMPT_MAX_CHARS = 600  # Whisper przyjmuje ~224 tokeny podpowiedzi


class STTError(Exception):
    pass


def vocabulary_prompt(settings: Settings) -> str:
    """Podpowiedź dla Whispera: słowa, które ma rozpoznawać poprawnie (imiona, nazwy własne)."""
    words = ["Hej Jarvis"]
    for contact in settings.contacts:
        words.append(contact.display_name)
        words.extend(contact.aliases)
    words.extend(settings.voice.vocabulary)
    prompt = ""
    for word in dict.fromkeys(w.strip() for w in words if w.strip()):
        candidate = f"{prompt}, {word}" if prompt else word
        if len(candidate) > _PROMPT_MAX_CHARS:
            break
        prompt = candidate
    return prompt + "."


def to_wav(pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buffer.getvalue()


class WhisperSTT:
    def __init__(
        self,
        api_key: Callable[[], str | None],
        settings: Callable[[], Settings],
        session: requests.Session | None = None,
    ):
        self._api_key = api_key
        self._settings = settings
        self._session = session or requests.Session()

    def transcribe(self, pcm: np.ndarray) -> str:
        key = self._api_key()
        if not key:
            raise STTError("Brak klucza GROQ_API_KEY – nie mogę rozpoznać mowy.")
        settings = self._settings()
        try:
            response = self._session.post(
                TRANSCRIPTIONS_URL,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("speech.wav", to_wav(pcm), "audio/wav")},
                data={
                    "model": settings.voice.stt_model,
                    "language": "pl",
                    "prompt": vocabulary_prompt(settings),
                    "response_format": "json",
                    "temperature": "0",
                },
                timeout=20,
            )
        except requests.RequestException as e:
            raise STTError("Brak połączenia z usługą rozpoznawania mowy.") from e
        if response.status_code == 429:
            raise STTError("Przekroczono limit rozpoznawania mowy. Spróbuj za chwilę.")
        if response.status_code != 200:
            log.error("Whisper HTTP %s: %s", response.status_code, response.text[:300])
            raise STTError(f"Rozpoznawanie mowy zwróciło błąd ({response.status_code}).")
        return str(response.json().get("text", "")).strip()
