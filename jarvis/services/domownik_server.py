"""Wbudowany serwer Domownika – aplikacja Flask pod waitressem, w wątku Jarvisa.

Domownik ma własny port (domyślnie 8080) i – przy `lan=True` – słucha w całej sieci domowej,
żeby telefony i PWA działały jak dotąd. Panel Jarvisa zostaje na 127.0.0.1: w sieci widać tylko Domownika.

Jeden proces, wiele wątków: `Store` Domownika serializuje zapisy przez `threading.RLock`, więc dwa procesy
nad tym samym plikiem (np. stary `start-serwer.bat` obok Jarvisa) nadpisywałyby sobie dane. Zajęty port
oznacza zwykle właśnie drugi serwer – wtedy nie startujemy i co chwilę próbujemy ponownie.
"""

import logging
import socket
import threading
from pathlib import Path
from typing import Any

from waitress import create_server, wasyncore
from waitress.task import ThreadedTaskDispatcher

from jarvis.events import EventBus
from jarvis.settings import SettingsStore

log = logging.getLogger(__name__)

# każde otwarte połączenie /api/zmiany (SSE) na stałe zajmuje jeden wątek – zapas na kilka urządzeń
THREADS = 16
RETRY_SECONDS = 10


def lan_ip() -> str:
    """Adres tego komputera w sieci domowej – do wpisania na telefonie."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))  # nic nie wysyła, system tylko wybiera interfejs wyjściowy
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class DomownikServer:
    def __init__(self, settings: SettingsStore, bus: EventBus, data_file: Path, app_factory=None):
        self._settings = settings
        self._bus = bus
        self._data_file = data_file
        self._app_factory = app_factory
        self._app = None
        self._lock = threading.Lock()  # zmiana konfiguracji (start/stop) – jedna naraz
        self._server_lock = threading.Lock()  # przekazanie gotowego serwera między wątkami
        self._config: tuple[bool, str, int] | None = None
        self._started = False  # zmiany ustawień obchodzą serwer dopiero po start() (np. nie w testach API)
        self._stop = threading.Event()
        self._server = None
        self._thread: threading.Thread | None = None
        self._state = "off"
        self._error = ""
        bus.subscribe(lambda _: self._apply_async(), {"settings.changed"})

    # --- cykl życia ---

    def start(self) -> None:
        self._started = True
        self._apply()

    def close(self) -> None:
        with self._lock:
            self._started = False
            self._shutdown()
            self._config = None

    def _apply_async(self) -> None:
        # zdarzenie przychodzi w wątku zapisu ustawień – restart serwera nie może go blokować
        threading.Thread(target=self._apply, name="domownik-apply", daemon=True).start()

    def _apply(self) -> None:
        s = self._settings.get().domownik
        config = (s.serve, "0.0.0.0" if s.lan else "127.0.0.1", s.port)
        with self._lock:
            if not self._started or config == self._config:
                return
            self._shutdown()
            self._config = config
            if s.serve:
                self._stop = threading.Event()
                self._thread = threading.Thread(
                    target=self._run, args=(config[1], config[2], self._stop), name="domownik", daemon=True
                )
                self._state = "starting"
                self._thread.start()
            else:
                self._set_state("off")

    def _run(self, host: str, port: int, stop: threading.Event) -> None:
        try:
            app = self._flask_app()
        except Exception as exc:
            log.exception("Nie udało się wczytać Domownika")
            self._set_state("error", f"Nie udało się wczytać danych Domownika: {exc}")
            return
        warned = False
        while not stop.is_set():
            # własny dyspozytor bez wątków: create_server uruchamia je PRZED zajęciem portu, więc każda
            # nieudana próba zostawiałaby 16 osieroconych wątków
            dispatcher = ThreadedTaskDispatcher()
            try:
                server = create_server(app, host=host, port=port, ident="Domownik", _dispatcher=dispatcher)
            except OSError as exc:
                error = f"Port {port} jest zajęty – czy stary Domownik (start-serwer.bat) nadal działa?"
                log.warning("Domownik nie wystartował na %s:%s: %s", host, port, exc)
                with self._server_lock:
                    if stop.is_set():
                        return
                    self._set_state("error", error)
                if not warned:
                    self._bus.notice(f"{error} Zamknij go albo zmień port w Ustawieniach.", "warning")
                    warned = True
                stop.wait(RETRY_SECONDS)
                continue
            with self._server_lock:
                if stop.is_set():  # zamknięto w trakcie startu
                    _close(server)
                    return
                self._server = server
                # stan zmieniamy pod blokadą, sprawdziwszy stop – „running” nie nadpisze „off” z _shutdown
                self._set_state("running")
            dispatcher.set_thread_count(THREADS)
            log.info("Domownik działa na http://%s:%s (dane: %s)", host, port, self._data_file)
            server.run()
            return

    def _flask_app(self):
        if self._app is None:
            if self._app_factory is None:
                from jarvis.domownik import create_app  # import opóźniony: Flask tylko, gdy serwer jest włączony

                self._app_factory = create_app
            self._app = self._app_factory(self._data_file)
        return self._app

    def _shutdown(self) -> None:
        """Zatrzymuje działający serwer (woła się pod self._lock)."""
        self._stop.set()
        with self._server_lock:
            server, self._server = self._server, None
            self._state, self._error = "off", ""
        thread, self._thread = self._thread, None
        if server is not None:
            _close(server, self._app)
        if thread is not None:
            thread.join(5)

    # --- stan ---

    def _set_state(self, state: str, error: str = "") -> None:
        self._state, self._error = state, error
        self._bus.publish("domownik.status", **self.status())

    def status(self) -> dict[str, Any]:
        s = self._settings.get().domownik
        return {
            "serve": s.serve,
            "state": self._state,
            "error": self._error,
            "url": s.base_url,
            "lan_url": f"http://{lan_ip()}:{s.port}" if s.serve and s.lan else "",
        }


def _close(server, app=None) -> None:
    """waitress nie ma „stop”: zamykamy wszystkie gniazda pętli (pętla kończy się przy pustej mapie),
    a potem gasimy wątki robocze."""
    wasyncore.close_all(server._map)
    if app is not None:
        # budzi połączenia SSE czekające na zmianę – zapis do zamkniętego gniazda kończy ich wątki od razu
        app.extensions["domownik"]["zmiany"].bump()
    server.task_dispatcher.shutdown(timeout=2)
