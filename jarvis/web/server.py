"""Serwer interfejsu: REST + WebSocket (zdarzenia na żywo) + pliki statyczne UI.

Działa tylko na 127.0.0.1 – interfejs jest dla lokalnego okna/przeglądarki.
"""

import asyncio
import contextlib
import logging
import mimetypes
import threading
import time
from collections import deque
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from jarvis import paths
from jarvis.app import JarvisApp
from jarvis.events import Event, EventBus
from jarvis.llm import LLMError
from jarvis.services.calendar_store import CalendarError
from jarvis.settings import SECRET_KEYS, SettingsError

log = logging.getLogger(__name__)

HISTORY_TOPICS = {"transcript", "reply", "tool", "discord.message", "reminder", "notice"}
MAX_QUEUE = 500

# Windows potrafi mieć w rejestrze .js jako text/plain – przeglądarka odrzuciłaby wtedy moduły ES
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class WebSocketHub:
    """Przekazuje zdarzenia z szyny (wątki backendu) do wszystkich podłączonych klientów."""

    def __init__(self, bus: EventBus):
        self.history: deque[dict[str, Any]] = deque(maxlen=100)
        self._clients: set[tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = set()
        self._lock = threading.Lock()
        bus.subscribe(self._on_event)

    def _on_event(self, event: Event) -> None:
        message = event.to_dict()
        if event.topic in HISTORY_TOPICS:
            self.history.append(message)
        with self._lock:
            clients = list(self._clients)
        for queue, loop in clients:
            with contextlib.suppress(RuntimeError):  # pętla klienta już zamknięta
                loop.call_soon_threadsafe(self._put, queue, message)

    @staticmethod
    def _put(queue: asyncio.Queue, message: dict[str, Any]) -> None:
        if queue.qsize() < MAX_QUEUE or message["topic"] != "audio.level":
            queue.put_nowait(message)

    def register(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._clients.add((queue, loop))

    def unregister(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._clients.discard((queue, loop))


def _error(status: int, detail: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"detail": detail, **extra}, status_code=status)


def _parse_day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"Nieprawidłowa data ({name}): {value}") from None


def create_app(jarvis: JarvisApp) -> FastAPI:
    api = FastAPI(title="Jarvis", docs_url=None, redoc_url=None)
    hub = WebSocketHub(jarvis.bus)

    @lru_cache(maxsize=1)
    def voices() -> list[dict[str, str]]:
        from jarvis.audio.tts import EdgeTTS

        return EdgeTTS.list_voices()

    # --- stan i polecenia ---

    @api.get("/api/status")
    def status() -> dict[str, Any]:
        return jarvis.status()

    @api.post("/api/command")
    def command(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "Puste polecenie.")
        return {"reply": jarvis.respond(text, "text")}

    # --- kalendarz ---

    @api.get("/api/calendar/events")
    def list_events() -> dict[str, Any]:
        return {"events": jarvis.calendar.all_events()}

    @api.get("/api/calendar/occurrences")
    def occurrences(start: str, end: str) -> dict[str, Any]:
        first, last = _parse_day(start, "start"), _parse_day(end, "end")
        if last < first or last - first > timedelta(days=100):
            raise HTTPException(400, "Nieprawidłowy zakres dat (maksymalnie 100 dni).")
        return {"occurrences": [o.to_dict() for o in jarvis.calendar.occurrences(first, last)]}

    @api.post("/api/calendar/events", status_code=201, response_model=None)
    def add_event(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
        try:
            return {"event": jarvis.calendar.add(body)}
        except CalendarError as e:
            return _error(400, str(e))

    @api.put("/api/calendar/events/{event_id}", response_model=None)
    def update_event(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
        try:
            event = jarvis.calendar.update(event_id, body)
        except CalendarError as e:
            return _error(400, str(e))
        if event is None:
            return _error(404, "Nie znaleziono wydarzenia.")
        return {"event": event}

    @api.delete("/api/calendar/events/{event_id}", status_code=204, response_model=None)
    def delete_event(event_id: str) -> Response | JSONResponse:
        if not jarvis.calendar.remove(event_id):
            return _error(404, "Nie znaleziono wydarzenia.")
        return Response(status_code=204)

    # --- ustawienia ---

    @api.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return {"settings": jarvis.settings.get().to_dict(), "secrets": jarvis.secrets.masked()}

    @api.put("/api/settings", response_model=None)
    def put_settings(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
        try:
            return {"settings": jarvis.settings.update(body).to_dict()}
        except SettingsError as e:
            return _error(400, " ".join(e.errors), errors=e.errors)

    @api.put("/api/secrets", response_model=None)
    def put_secrets(body: dict[str, Any] = Body(...)) -> dict[str, Any] | JSONResponse:
        unknown = [k for k in body if k not in SECRET_KEYS]
        if unknown:
            return _error(400, f"Nieznane klucze: {', '.join(unknown)}.")
        for key, value in body.items():
            if isinstance(value, str) and value.strip():
                jarvis.secrets.set(key, value)
        jarvis.publish_status()
        return {"secrets": jarvis.secrets.masked()}

    @api.get("/api/llm/models", response_model=None)
    def llm_models() -> dict[str, Any] | JSONResponse:
        try:
            models = jarvis.llm.list_models()
        except LLMError as e:
            return _error(502, str(e))
        return {"models": models, "current": jarvis.settings.get().llm.model}

    # --- dźwięk ---

    @api.get("/api/tts/voices", response_model=None)
    def tts_voices() -> dict[str, Any] | JSONResponse:
        try:
            return {"voices": voices()}
        except Exception as e:
            log.exception("Lista głosów niedostępna")
            return _error(502, f"Nie udało się pobrać listy głosów: {e}")

    @api.post("/api/tts/preview", status_code=204, response_model=None)
    def tts_preview(body: dict[str, Any] = Body(...)) -> Response | JSONResponse:
        if not jarvis.voice:
            return _error(409, "Dźwięk jest wyłączony (--no-voice).")
        voice = str(body.get("voice") or jarvis.settings.get().voice.tts_voice)
        rate = int(body.get("rate") or 0)
        jarvis.voice.preview(voice, rate, body.get("text"))
        return Response(status_code=204)

    @api.get("/api/audio/devices")
    def audio_devices() -> dict[str, Any]:
        from jarvis.audio.devices import list_devices

        return list_devices()

    # --- zdarzenia na żywo ---

    @api.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        hub.register(queue, loop)

        async def sender() -> None:
            while True:
                await ws.send_json(await queue.get())

        send_task = asyncio.create_task(sender())
        try:
            hello = {"state": jarvis.tracker.state, "status": jarvis.status(), "history": list(hub.history)}
            await ws.send_json({"topic": "hello", "data": hello, "ts": time.time()})
            while True:
                await _handle_client_message(jarvis, await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unregister(queue, loop)
            send_task.cancel()

    api.mount("/", StaticFiles(directory=paths.STATIC_DIR, html=True), name="static")
    return api


async def _handle_client_message(jarvis: JarvisApp, message: Any) -> None:
    if not isinstance(message, dict):
        return
    if message.get("type") == "command":
        text = str(message.get("text", "")).strip()
        if text:
            # w tle – WebSocket nie może czekać na odpowiedź modelu
            task = asyncio.create_task(asyncio.to_thread(jarvis.respond, text, "text"))
            task.add_done_callback(_log_task_error)
    elif message.get("type") == "voice" and jarvis.voice:
        action = message.get("action")
        if action == "mute":
            jarvis.voice.set_muted(True)
        elif action == "unmute":
            jarvis.voice.set_muted(False)
        elif action == "listen":
            jarvis.voice.listen()
        elif action == "stop":
            jarvis.voice.stop_speaking()


def _log_task_error(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        log.error("Błąd polecenia z UI", exc_info=task.exception())


class WebServer:
    """Uvicorn w wątku w tle (główny wątek należy do okna pywebview)."""

    def __init__(self, app: FastAPI, host: str, port: int):
        self.url = f"http://{host}:{port}/"
        self._server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", ws="auto"))

    def start(self, timeout: float = 10.0) -> None:
        threading.Thread(target=self._server.run, name="web", daemon=True).start()
        deadline = time.time() + timeout
        while not self._server.started:
            if time.time() > deadline:
                raise RuntimeError("Serwer interfejsu nie wystartował.")
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
