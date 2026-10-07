"""Pętla głosowa: słowo wywołania → nagranie → transkrypcja → odpowiedź, z przerywaniem.

Wątek mikrofonu (`process_frame`, co 80 ms) tylko wykrywa i nagrywa – nigdy nie czeka na sieć.
Transkrypcja i odpowiedź (LLM + mówienie) dzieją się w osobnym wątku roboczym, dzięki czemu
w trakcie mówienia Jarvisa mikrofon dalej nasłuchuje i może go przerwać.

Stany nasłuchu: idle → (wake word / przycisk) → listening → [transcribing → thinking → speaking]
→ follow_up (kilka sekund, można mówić bez „Hej Jarvis”) → idle.
"""

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from jarvis.audio.bargein import DUCK_GAIN, DuckTest, EchoGate
from jarvis.audio.devices import rms, ui_level
from jarvis.audio.recorder import SPEECH_ON, UtteranceRecorder
from jarvis.audio.stt import STTError, vocabulary_prompt
from jarvis.audio.transcript import clean_transcript, has_wake_phrase, is_echo
from jarvis.events import Event, EventBus
from jarvis.settings import SettingsStore
from jarvis.state import StatusTracker

log = logging.getLogger(__name__)

PREROLL_FRAMES = 16  # ~1,3 s dźwięku sprzed wykrycia (żeby nie uciąć początku polecenia)
BARGE_IN_PREROLL_FRAMES = 10  # obejmuje początek mowy, wykrycie i test ściszenia
WAKE_COOLDOWN = 2.0
# „Miękkie” wykrycie: model bywa niepewny, gdy polecenie następuje bez pauzy („Hej Jarvis, która…”).
# Wynik powyżej progu × SOFT_WAKE_RATIO uruchamia ciche nagranie, a Whisper sprawdza, czy padło „Jarvis”.
SOFT_WAKE_RATIO = 0.4
SOFT_WAKE_WINDOW = 3  # tyle ramek czekamy, czy wynik nie przekroczy jednak pełnego progu
# „Hej Jarvis” to mowa: wykrycie liczy się tylko, gdy VAD słyszał mowę w ostatniej ~1 s. Bez tego w ciszy
# detektor potrafi dać fałszywy alarm na szumie mikrofonu, a Whisper na ciszy powtarza podpowiedź „Hej Jarvis.”.
WAKE_SPEECH_WINDOW = 12  # ramek po 80 ms
WAKE_SPEECH_FRAMES = 1  # pełne wykrycie
SOFT_WAKE_SPEECH_FRAMES = 2  # miękkie – słabszy dowód, więc więcej mowy
FOLLOW_UP_VOICE_FRAMES = 2
QUESTION_FOLLOW_UP_SECONDS = 10.0  # po pytaniu Jarvisa („Ile wcześniej przypomnieć?”) czekamy dłużej
MIC_LEVEL_REFERENCE = 0.05
MIN_VOICE_LEVEL = 0.004


@dataclass(frozen=True)
class BargeIn:
    """Użytkownik przerwał wypowiedź Jarvisa."""

    spoken: str  # co zdążyło paść
    kind: str  # reply | notice
    full_text: str = ""  # cała przerwana wypowiedź (do odrzucenia echa)


@dataclass(frozen=True)
class _Job:
    audio: np.ndarray
    barge_in: BargeIn | None
    require_wake: bool = False  # miękkie wykrycie – transkrypcja musi zawierać „Jarvis”


Respond = Callable[[str, BargeIn | None], None]


class VoiceLoop:
    def __init__(
        self,
        *,
        mic,
        wake,
        vad,
        stt,
        speaker,
        player,
        tracker: StatusTracker,
        settings: SettingsStore,
        bus: EventBus,
        respond: Respond,
        chime: Callable[[], None] = lambda: None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.mic = mic
        self._wake = wake
        self._vad = vad
        self._stt = stt
        self._speaker = speaker
        self._player = player
        self._tracker = tracker
        self._settings = settings
        self._bus = bus
        self._respond = respond
        self._chime = chime
        self._clock = clock

        self._cfg = settings.get()
        self._muted = not self._cfg.voice.listen
        self._preroll: deque[np.ndarray] = deque(maxlen=PREROLL_FRAMES)
        self._recorder: UtteranceRecorder | None = None
        self._record_mode = ""
        self._barge_in: BargeIn | None = None
        self._duck_test: DuckTest | None = None
        self._gate = EchoGate()
        self._jobs: queue.Queue[_Job] = queue.Queue()
        self._pending_lock = threading.Lock()
        self._pending = 0
        self._follow_up_until = 0.0
        self._wake_blocked_until = 0.0
        self._noise_floor = 0.003
        self._voice_frames = 0
        self._trigger_requested = False
        self._soft_frames: int | None = None
        self._recent_vad: deque[float] = deque(maxlen=WAKE_SPEECH_WINDOW)

        speaker.on_end = self._on_speech_end
        bus.subscribe(self._on_settings_changed, {"settings.changed"})
        self._set_listener("muted" if self._muted else "idle")

    # --- sterowanie z zewnątrz ---

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        if muted:
            self._cancel_recording()
        else:
            self._wake.reset()
        self._set_listener("muted" if muted else "idle")
        self._bus.publish("voice.status")  # UI odświeży stan mikrofonu

    def trigger(self) -> None:
        """Przycisk „Mów” – jak słowo wywołania."""
        if self._muted:
            self.set_muted(False)
        self._trigger_requested = True

    # --- pętle ---

    def run(self, stop: threading.Event) -> None:
        threading.Thread(target=self._worker, args=(stop,), name="voice-worker", daemon=True).start()
        while not stop.is_set():
            frame = self.mic.read(timeout=0.5)
            if frame is not None:
                try:
                    self.process_frame(frame)
                except Exception:
                    log.exception("Błąd przetwarzania dźwięku")

    def process_frame(self, frame: np.ndarray) -> None:
        if self._muted:
            return
        now = self._clock()
        level = rms(frame)
        wake_score = self._wake.score(frame)
        vad = self._vad.probability(frame)
        self._recent_vad.append(vad)
        self._bus.publish(
            "audio.level", source="mic", level=ui_level(level, MIC_LEVEL_REFERENCE), wake=round(wake_score, 3)
        )

        if self._recorder is not None:
            self._preroll.append(frame)
            self._continue_recording(frame, vad, level)
            return
        self._preroll.append(frame)

        wake_hit = wake_score >= self._cfg.voice.wake_threshold and now >= self._wake_blocked_until
        if wake_hit and self._speech_frames() < WAKE_SPEECH_FRAMES:
            log.info("Odrzucono „Hej Jarvis” bez mowy (wynik %.2f) – fałszywy alarm na szumie", wake_score)
            self._wake.reset()
            wake_hit = False
        if wake_hit:
            log.info("Słowo wywołania (wynik %.2f)", wake_score)
            self._wake.reset()
            self._wake_blocked_until = now + WAKE_COOLDOWN

        if self._speaker.is_speaking:
            self._while_speaking(level, vad, wake_hit)
            return
        self._duck_test = None
        self._gate.reset_candidate()

        if self._busy:
            return  # trwa transkrypcja albo myślenie

        if vad < 0.2:
            self._noise_floor = max(0.0005, 0.98 * self._noise_floor + 0.02 * level)

        if wake_hit or self._consume_trigger():
            self._soft_frames = None
            self._chime()
            self._start_recording("command", wait_for_speech=True)
            return

        if self._soft_frames is not None:
            self._soft_frames += 1
            if self._soft_frames >= SOFT_WAKE_WINDOW:
                self._soft_frames = None
                if self._speech_frames() < SOFT_WAKE_SPEECH_FRAMES:
                    log.debug("Miękkie wykrycie bez mowy – pomijam")
                    return
                # po cichu: kula pokaże „słucham” dopiero, gdy Whisper potwierdzi „Jarvis”
                self._start_recording("tentative", speech_ongoing=True, quiet=True)
            return
        if wake_score >= self._cfg.voice.wake_threshold * SOFT_WAKE_RATIO and now >= self._wake_blocked_until:
            self._soft_frames = 0
            return

        if now < self._follow_up_until:
            loud = vad >= 0.6 and level > max(self._noise_floor * 3, MIN_VOICE_LEVEL)
            self._voice_frames = self._voice_frames + 1 if loud else 0
            if self._voice_frames >= FOLLOW_UP_VOICE_FRAMES:
                self._voice_frames = 0
                self._start_recording("command", preroll=6)
            else:
                self._set_listener("follow_up")
        else:
            self._set_listener("idle")

    # --- przerywanie ---

    def _while_speaking(self, level: float, vad: float, wake_hit: bool) -> None:
        mode = self._cfg.voice.barge_in
        if mode == "off":
            return
        if wake_hit:
            self._confirm_barge_in()
            return
        if mode != "any":
            return

        if self._duck_test is None:
            if self._gate.update(level, vad, self._player.output_level, self._noise_floor):
                self._player.duck(DUCK_GAIN)
                self._duck_test = DuckTest(coupling=self._gate.coupling, noise_floor=self._noise_floor)
            return

        verdict = self._duck_test.add(level, self._player.output_level)
        if verdict is None:
            return
        self._duck_test = None
        self._gate.reset_candidate()
        log.info("Test ściszenia: %s", verdict)
        if verdict == "user":
            self._confirm_barge_in()
            return
        # echo albo niepewne – mówimy dalej. Przy niepewnym wyniku nie ryzykujemy: gdy echo jest
        # głośniejsze od użytkownika, transkrypcja bywa halucynacją. Wtedy przerywa „Hej Jarvis”.
        self._player.unduck()
        if verdict == "echo":
            self._gate.penalize()

    def _current_barge_in(self) -> BargeIn:
        return BargeIn(self._speaker.spoken_so_far(), self._speaker.current_kind, self._speaker.current_text)

    def _confirm_barge_in(self) -> None:
        barge_in = self._current_barge_in()
        log.info("Przerwanie wypowiedzi po: „%s”", barge_in.spoken)
        self._speaker.stop()
        self._start_recording("command", preroll=BARGE_IN_PREROLL_FRAMES, speech_ongoing=True, barge_in=barge_in)

    # --- nagrywanie ---

    def _start_recording(
        self,
        mode: str,
        *,
        preroll: int = PREROLL_FRAMES,
        wait_for_speech: bool = False,
        speech_ongoing: bool = False,
        barge_in: BargeIn | None = None,
        quiet: bool = False,
    ) -> None:
        recorder = UtteranceRecorder(preroll=list(self._preroll)[-preroll:])
        # po „Hej Jarvis” czekamy na nową mowę (użytkownik może zrobić pauzę przed poleceniem);
        # przy przerwaniu i follow-upie mowa już trwa
        recorder.speech_started = speech_ongoing or not wait_for_speech
        if speech_ongoing:
            recorder.speech_frames = 3  # mowa została już potwierdzona przed rozpoczęciem nagrania
        self._recorder = recorder
        self._record_mode = mode
        self._barge_in = barge_in
        if not quiet:
            self._set_listener("listening")

    def _continue_recording(self, frame: np.ndarray, vad: float, level: float) -> None:
        recorder = self._recorder
        if recorder is None or not recorder.add(frame, vad, level):
            return
        self._recorder = None
        if not recorder.has_speech:
            self._set_listener("idle")
            return
        log.info("Koniec wypowiedzi (%s, %.1f s nagrania)", self._record_mode, recorder.duration)
        with self._pending_lock:
            self._pending += 1
        self._jobs.put(_Job(recorder.audio(), self._barge_in, require_wake=self._record_mode == "tentative"))

    def _cancel_recording(self) -> None:
        self._recorder = None

    # --- wątek roboczy ---

    @property
    def _busy(self) -> bool:
        with self._pending_lock:
            return self._pending > 0

    def _worker(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                job = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.process_job(job)
            except Exception:
                log.exception("Błąd obsługi wypowiedzi")
            finally:
                with self._pending_lock:
                    self._pending -= 1
                if not self._busy and self._recorder is None and not self._speaker.is_speaking:
                    self._set_listener("idle")

    def process_job(self, job: _Job) -> None:
        self._tracker.set_transcribing(True)
        started = time.monotonic()
        try:
            raw = self._stt.transcribe(job.audio)
        except STTError as e:
            self._bus.notice(str(e), "error")
            return
        finally:
            self._tracker.set_transcribing(False)

        text = clean_transcript(raw, vocabulary_prompt(self._cfg))
        log.info("Rozpoznano w %.0f ms: „%s” → „%s”", (time.monotonic() - started) * 1000, raw, text)
        if job.require_wake:
            if not has_wake_phrase(raw):
                return  # model się pomylił – to nie było do Jarvisa
            if not text:
                self._trigger_requested = True  # samo „Hej Jarvis” – słuchamy polecenia
                return
        barge_in = job.barge_in
        if barge_in is not None and barge_in.full_text and is_echo(raw, barge_in.full_text):
            # Jarvis już przestał mówić, ale nie odpowiadamy na własne słowa
            log.info("Przerwanie okazało się echem – ignoruję")
            self._gate.penalize()
            return
        if text:
            self._respond(text, barge_in)

    # --- pomocnicze ---

    def _on_speech_end(self, result) -> None:
        if result.interrupted:
            return
        seconds = self._cfg.voice.follow_up_seconds
        if result.kind == "reply" and result.text.rstrip().endswith("?"):
            # Jarvis o coś zapytał – odpowiedź bez „Hej Jarvis”, nawet gdy follow-up jest wyłączony
            seconds = max(seconds, QUESTION_FOLLOW_UP_SECONDS)
        if seconds > 0:
            self._follow_up_until = self._clock() + seconds

    def _on_settings_changed(self, event: Event) -> None:
        previous = self._cfg
        self._cfg = self._settings.get()
        if previous.voice.listen != self._cfg.voice.listen:
            self.set_muted(not self._cfg.voice.listen)

    def _speech_frames(self) -> int:
        """Ile ramek z mową było w ostatniej ~1 s."""
        return sum(p >= SPEECH_ON for p in self._recent_vad)

    def _consume_trigger(self) -> bool:
        triggered, self._trigger_requested = self._trigger_requested, False
        return triggered

    def _set_listener(self, state: str) -> None:
        self._tracker.set_listener(state)
