"""Składanie modułu głosowego: mówienie jest dostępne zawsze, nasłuch – gdy działa mikrofon i modele."""

import logging
import threading
import time
from pathlib import Path
from typing import Any

from jarvis.audio.chime import CHIME
from jarvis.audio.devices import resolve_device, suppress_alsa_errors
from jarvis.audio.mic import MicStream
from jarvis.audio.player import Player
from jarvis.audio.speaker import Speaker
from jarvis.audio.stt import WhisperSTT
from jarvis.audio.tts import EdgeTTS
from jarvis.audio.voice_loop import Respond, VoiceLoop
from jarvis.audio.wakeword import VoiceActivityDetector, WakeWordDetector, ensure_models, models_present
from jarvis.events import Event, EventBus
from jarvis.settings import Secrets, SettingsStore
from jarvis.state import StatusTracker

log = logging.getLogger(__name__)


class VoiceService:
    def __init__(
        self,
        settings: SettingsStore,
        secrets: Secrets,
        bus: EventBus,
        tracker: StatusTracker,
        models_dir: Path,
        respond: Respond,
    ):
        self._settings = settings
        self._secrets = secrets
        self._bus = bus
        self._tracker = tracker
        self._models_dir = models_dir
        self._respond = respond
        self.player = Player(bus, device=self._output_device, volume=lambda: settings.get().voice.volume)
        self.tts = EdgeTTS()
        self.speaker = Speaker(self.tts, self.player, bus, tracker, settings)
        self.loop: VoiceLoop | None = None
        self.error: str | None = None
        self._input_device = settings.get().voice.input_device
        bus.subscribe(self._on_settings_changed, {"settings.changed"})

    def _output_device(self) -> int | None:
        return resolve_device(self._settings.get().voice.output_device, "output")

    # --- uruchomienie ---

    def start(self, stop: threading.Event) -> None:
        threading.Thread(target=self._warm_up_tts, name="tts-warmup", daemon=True).start()
        threading.Thread(target=self._run, args=(stop,), name="voice", daemon=True).start()

    def _warm_up_tts(self) -> None:
        """Pierwsze połączenie z usługą mowy w procesie trwa 2–3 s (DNS, TLS, inicjalizacja) –
        robimy je od razu przy starcie, żeby pierwsza odpowiedź nie czekała."""
        started = time.monotonic()
        self.player.prepare()
        try:
            self.tts.synthesize("Gotowy.", voice=self._settings.get().voice.tts_voice)
            log.info("Synteza mowy gotowa (rozgrzewka %.1f s)", time.monotonic() - started)
        except Exception as e:
            log.warning("Rozgrzewka syntezy mowy nie powiodła się: %s", e)

    def _run(self, stop: threading.Event) -> None:
        suppress_alsa_errors()
        try:
            if not models_present(self._models_dir):
                self._bus.notice("Pobieram modele rozpoznawania „Hey Jarvis” (jednorazowo)…")
            ensure_models(self._models_dir)
            wake = WakeWordDetector(self._models_dir)
            vad = VoiceActivityDetector(self._models_dir)
            mic = MicStream(resolve_device(self._input_device, "input"))
            mic.start()
        except Exception as e:
            log.exception("Nasłuch niedostępny")
            self._fail(f"Nasłuch niedostępny: {e}")
            return

        self.loop = VoiceLoop(
            mic=mic,
            wake=wake,
            vad=vad,
            stt=WhisperSTT(lambda: self._secrets.groq_api_key, self._settings.get),
            speaker=self.speaker,
            player=self.player,
            tracker=self._tracker,
            settings=self._settings,
            bus=self._bus,
            respond=self._respond,
            chime=lambda: self.player.play_effect(CHIME),
        )
        self._publish_status()
        log.info("Nasłuch uruchomiony")
        try:
            self.loop.run(stop)
        finally:
            self.loop.mic.stop()

    def _fail(self, message: str) -> None:
        self.error = message
        self._tracker.set_listener("offline")
        self._bus.notice(message, "error")
        self._publish_status()

    def _on_settings_changed(self, event: Event) -> None:
        device = self._settings.get().voice.input_device
        if device != self._input_device and self.loop is not None:
            self._input_device = device
            self._switch_microphone(device)

    def _switch_microphone(self, device_name: str) -> None:
        try:
            new_mic = MicStream(resolve_device(device_name, "input"))
            new_mic.start()
        except Exception as e:
            self._bus.notice(f"Nie mogę otworzyć mikrofonu: {e}", "error")
            return
        old, self.loop.mic = self.loop.mic, new_mic
        old.stop()

    # --- sterowanie z UI ---

    def status(self) -> dict[str, Any]:
        return {
            "available": self.loop is not None,
            "listening": self.loop is not None and not self.loop.muted,
            "muted": self.loop.muted if self.loop else False,
            "error": self.error,
        }

    def _publish_status(self) -> None:
        self._bus.publish("voice.status")  # aplikacja publikuje wtedy pełny stan (topic "status")

    def set_muted(self, muted: bool) -> None:
        if self.loop:
            self.loop.set_muted(muted)

    def listen(self) -> None:
        if self.loop:
            self.loop.trigger()

    def stop_speaking(self) -> None:
        self.speaker.stop()

    def close(self) -> None:
        self.speaker.stop()
        self.player.close()

    def say(self, text: str, kind: str = "notice") -> None:
        self.speaker.say_async(text, kind)

    def preview(self, voice: str, rate: int, pitch: int = 0, text: str | None = None) -> None:
        # przerywamy poprzednią próbkę, żeby przy szybkim przełączaniu głosów było słychać od razu nowy
        self.speaker.stop()
        sample = text or "Cześć, tu Jarvis. Tak teraz brzmię – daj znać, czy ci się podoba."
        self.speaker.say_async(sample, "notice", voice=voice, rate=rate, pitch=pitch)
