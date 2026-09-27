"""Synteza mowy przez edge-tts (neuronowe głosy Microsoftu) z czasami słów."""

import asyncio
import logging
import re
from dataclasses import dataclass, field

import miniaudio
import numpy as np

log = logging.getLogger(__name__)

TTS_SAMPLE_RATE = 24000


class TTSError(Exception):
    pass


@dataclass(frozen=True)
class WordMark:
    text: str
    start: float  # sekundy od początku fragmentu
    char_end: int  # koniec słowa w tekście fragmentu


@dataclass
class Speech:
    """Zsyntezowany fragment (zwykle jedno zdanie)."""

    text: str
    samples: np.ndarray  # float32, mono, TTS_SAMPLE_RATE
    words: list[WordMark] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.samples.size / TTS_SAMPLE_RATE


def split_sentences(text: str, min_chars: int = 25) -> list[str]:
    """Dzieli tekst na zdania, łącząc bardzo krótkie z następnymi – pierwsze zdanie syntezujemy
    i odtwarzamy od razu, a kolejne w tym czasie się generują."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


def locate_words(text: str, words: list[tuple[str, float]]) -> list[WordMark]:
    """Dopasowuje słowa z edge-tts do pozycji w tekście (potrzebne do napisów i przerwań)."""
    marks = []
    cursor = 0
    lower = text.lower()
    for word, start in words:
        idx = lower.find(word.lower(), cursor)
        if idx >= 0:
            cursor = idx + len(word)
        marks.append(WordMark(word, start, cursor))
    return marks


def decode_mp3(data: bytes) -> np.ndarray:
    decoded = miniaudio.decode(
        data, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=TTS_SAMPLE_RATE
    )
    return np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0


DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"  # wielojęzyczny: naturalny, ciepły głos, dobrze mówi po polsku


def voice_entries(voices: list[dict], locale_prefix: str = "pl-") -> list[dict[str, str]]:
    """Głosy do wyboru: polskie oraz wielojęzyczne (mówią po polsku, często naturalniej)."""
    result = []
    for v in voices:
        name = v["ShortName"]
        multilingual = "Multilingual" in name
        if not (v["Locale"].lower().startswith(locale_prefix) or multilingual):
            continue
        label = name.split("-", 2)[-1].removesuffix("Neural").replace("Multilingual", "")
        if multilingual:
            label += " (wielojęzyczny)"
        result.append({"name": name, "label": label, "gender": v.get("Gender", "")})
    # najpierw polskie, potem wielojęzyczne; w grupach alfabetycznie
    return sorted(result, key=lambda v: (not v["name"].lower().startswith(locale_prefix), v["label"]))


class EdgeTTS:
    def __init__(self, voice: str = DEFAULT_VOICE, rate: int = 0):
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, voice: str | None = None, rate: int | None = None) -> Speech:
        import edge_tts

        voice = voice or self.voice
        rate = self.rate if rate is None else rate
        audio = bytearray()
        words: list[tuple[str, float]] = []
        try:
            communicate = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary="WordBoundary")
            for chunk in communicate.stream_sync():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    words.append((chunk["text"], chunk["offset"] / 1e7))  # jednostki 100 ns
        except Exception as e:
            raise TTSError(f"Synteza mowy nie powiodła się: {e}") from e
        if not audio:
            raise TTSError("Synteza mowy zwróciła pusty dźwięk.")
        return Speech(text, decode_mp3(bytes(audio)), locate_words(text, words))

    @staticmethod
    def list_voices() -> list[dict[str, str]]:
        import edge_tts

        return voice_entries(asyncio.run(edge_tts.list_voices()))
