"""Synteza mowy przez edge-tts (neuronowe głosy Microsoftu) z czasami słów."""

import asyncio
import logging
import re
import threading
import time
from collections import OrderedDict
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


# granice fraz: koniec zdania albo przecinek/średnik/dwukropek/myślnik
_PHRASE_BREAK = re.compile(r"(?<=[.!?…,;:–—])\s+")
FIRST_CHUNK_CHARS = 45
MIN_CHUNK_CHARS = 40
MAX_CHUNK_CHARS = 140
# kolejny fragment może być ~5× dłuższy od poprzedniego – tyle zdąży się wygenerować, zanim poprzedni wybrzmi
GROWTH = 5


def _cut_at_word(text: str, limit: int) -> tuple[str, str]:
    cut = text.rfind(" ", 15, limit + 1)
    # nie kończymy fragmentu przyimkiem ani spójnikiem („…plastiku w | temperaturze” brzmi nienaturalnie)
    while cut > 0 and len(text[:cut].rsplit(" ", 1)[-1]) <= 3:
        cut = text.rfind(" ", 15, cut)
    return (text[:cut], text[cut + 1 :]) if cut > 0 else (text, "")


def split_for_speech(text: str) -> list[str]:
    """Fragmenty do syntezy. Darmowa usługa Edge generuje cały fragment, zanim wyśle pierwszy dźwięk
    (ok. 1,3 s + ~12 ms na znak), więc pierwszy fragment jest krótki, kolejne coraz dłuższe, a wszystkie
    generują się równolegle – następny jest gotowy, zanim poprzedni wybrzmi."""
    phrases = [p for p in _PHRASE_BREAK.split(text.strip()) if p]
    chunks: list[str] = []
    limit = FIRST_CHUNK_CHARS
    current = ""
    while phrases:
        phrase = phrases.pop(0)
        candidate = f"{current} {phrase}" if current else phrase
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            phrases.insert(0, phrase)
        else:
            # sama fraza jest za długa – tniemy na granicy słowa
            current, rest = _cut_at_word(phrase, limit)
            if rest:
                phrases.insert(0, rest)
        chunks.append(current)
        limit = min(MAX_CHUNK_CHARS, max(MIN_CHUNK_CHARS, GROWTH * len(current)))
        current = ""
    if current:
        chunks.append(current)
    return chunks


def trim_silence(speech: "Speech", lead: float = 0.02, tail: float = 0.15, threshold: float = 0.004) -> "Speech":
    """Obcina ciszę na początku i końcu fragmentu (Edge dokleja ~0,1 s z przodu i ~0,5 s z tyłu),
    żeby między sklejanymi fragmentami nie było słychać przerw."""
    loud = np.flatnonzero(np.abs(speech.samples) > threshold)
    if loud.size == 0:
        return speech
    start = max(0, loud[0] - int(lead * TTS_SAMPLE_RATE))
    end = min(speech.samples.size, loud[-1] + int(tail * TTS_SAMPLE_RATE))
    shift = start / TTS_SAMPLE_RATE
    words = [WordMark(w.text, max(0.0, w.start - shift), w.char_end) for w in speech.words]
    return Speech(speech.text, speech.samples[start:end], words)


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
    CACHE_SIZE = 128  # powtarzalne frazy („Otwieram kalendarz.”) grają od razu

    def __init__(self, voice: str = DEFAULT_VOICE, rate: int = 0):
        self.voice = voice
        self.rate = rate
        self._cache: OrderedDict[tuple[str, str, int], Speech] = OrderedDict()
        self._cache_lock = threading.Lock()

    def synthesize(self, text: str, voice: str | None = None, rate: int | None = None) -> Speech:
        voice = voice or self.voice
        rate = self.rate if rate is None else rate
        key = (text, voice, rate)
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        speech = self._synthesize(text, voice, rate)
        with self._cache_lock:
            self._cache[key] = speech
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return speech

    def _synthesize(self, text: str, voice: str, rate: int) -> Speech:
        import edge_tts

        audio = bytearray()
        words: list[tuple[str, float]] = []
        started = time.monotonic()
        first_chunk = None
        try:
            communicate = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", boundary="WordBoundary")
            for chunk in communicate.stream_sync():
                if chunk["type"] == "audio":
                    if first_chunk is None:
                        first_chunk = time.monotonic() - started
                    audio += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    words.append((chunk["text"], chunk["offset"] / 1e7))  # jednostki 100 ns
        except Exception as e:
            raise TTSError(f"Synteza mowy nie powiodła się: {e}") from e
        if not audio:
            raise TTSError("Synteza mowy zwróciła pusty dźwięk.")
        log.debug("TTS %d znaków: pierwszy fragment %.0f ms, całość %.0f ms", len(text),
                  (first_chunk or 0) * 1000, (time.monotonic() - started) * 1000)
        return Speech(text, decode_mp3(bytes(audio)), locate_words(text, words))

    @staticmethod
    def list_voices() -> list[dict[str, str]]:
        import edge_tts

        return voice_entries(asyncio.run(edge_tts.list_voices()))
