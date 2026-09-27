"""Mówienie: tekst → krótkie fragmenty → synteza (równolegle, w tle) → odtwarzanie. Jedna wypowiedź naraz."""

import logging
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from jarvis.audio.player import Player
from jarvis.audio.speakable import speakable
from jarvis.audio.tts import EdgeTTS, Speech, TTSError, split_for_speech, trim_silence
from jarvis.events import EventBus
from jarvis.settings import SettingsStore
from jarvis.state import StatusTracker

log = logging.getLogger(__name__)

SYNTHESIS_WORKERS = 6
# tyle sekund mowy musi być gotowe przed startem (usługa generuje każdy fragment 1,3–3 s, czasem dłużej)
START_BUFFER_SECONDS = 2.0


def _pause_after(chunk: str, last: bool) -> float:
    """Pauza zostawiana po fragmencie – jak w naturalnej mowie: dłuższa po zdaniu, krótsza po przecinku,
    prawie żadna, gdy fragment urwano w środku frazy."""
    if last:
        return 0.5
    if chunk[-1] in ".!?…":
        return 0.35
    if chunk[-1] in ",;:–—":
        return 0.18
    return 0.05


@dataclass(frozen=True)
class SpeechResult:
    text: str
    kind: str  # reply | notice
    interrupted: bool
    spoken: str


class Speaker:
    def __init__(
        self,
        tts: EdgeTTS,
        player: Player,
        bus: EventBus,
        tracker: StatusTracker,
        settings: SettingsStore,
    ):
        self._tts = tts
        self._player = player
        self._bus = bus
        self._tracker = tracker
        self._settings = settings
        self._lock = threading.Lock()
        self.current_text = ""
        self.current_kind = ""
        self.on_end: Callable[[SpeechResult], None] | None = None

    @property
    def is_speaking(self) -> bool:
        return self._player.is_playing

    def spoken_so_far(self) -> str:
        return self._player.spoken_text(self.current_text)

    def stop(self) -> None:
        self._player.stop()

    def say(
        self,
        text: str,
        kind: str = "reply",
        voice: str | None = None,
        rate: int | None = None,
        pitch: int | None = None,
    ) -> SpeechResult:
        text = speakable(text.strip())
        if not text:
            return SpeechResult(text, kind, False, "")
        with self._lock:
            cfg = self._settings.get().voice
            voice = voice or cfg.tts_voice
            rate = cfg.tts_rate if rate is None else rate
            pitch = cfg.tts_pitch if pitch is None else pitch
            self.current_text, self.current_kind = text, kind
            self._tracker.set_speaking(True)
            self._bus.publish("tts.start", text=text)
            chunks = split_for_speech(text)
            # przy kilku fragmentach czekamy na zapas dźwięku – następne zdążą się wygenerować bez przerw
            min_start = START_BUFFER_SECONDS if len(chunks) > 1 else 0.0
            try:
                playback = self._player.play(self._segments(chunks, voice, rate, pitch), text, min_start)
            finally:
                self._tracker.set_speaking(False)
            result = SpeechResult(text, kind, playback.interrupted, playback.spoken)
            self._bus.publish("tts.end", interrupted=result.interrupted, spoken=result.spoken)
        if self.on_end:
            self.on_end(result)
        return result

    def say_async(self, text: str, kind: str = "notice", **kwargs) -> None:
        threading.Thread(target=self.say, args=(text, kind), kwargs=kwargs, daemon=True).start()

    def _segments(self, chunks: list[str], voice: str, rate: int, pitch: int) -> Iterator[Speech]:
        """Fragmenty generowane równolegle (usługa potrzebuje ~1,3 s+ na każdy), oddawane po kolei."""
        with ThreadPoolExecutor(max_workers=SYNTHESIS_WORKERS, thread_name_prefix="tts") as pool:
            futures = [
                pool.submit(self._tts.synthesize, chunk, voice=voice, rate=rate, pitch=pitch) for chunk in chunks
            ]
            try:
                for i, future in enumerate(futures):
                    speech = future.result()
                    yield trim_silence(speech, tail=_pause_after(chunks[i], last=i == len(futures) - 1))
            except TTSError as e:
                self._bus.notice(str(e), "error")
            finally:
                for future in futures:
                    future.cancel()
