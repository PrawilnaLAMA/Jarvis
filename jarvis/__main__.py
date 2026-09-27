"""Uruchomienie: python -m jarvis [--browser] [--no-voice] [--fullscreen] [--port N] [--debug]"""

import argparse
import logging
import socket
import sys
import time
import webbrowser
from logging.handlers import RotatingFileHandler

from jarvis import paths


def _setup_logging(debug: bool) -> None:
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    file = RotatingFileHandler(paths.LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[console, file],
    )
    for noisy in ("urllib3", "httpx", "websockets", "uvicorn.error", "pywebview"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _free_port(host: str, preferred: int) -> int:
    with socket.socket() as s:
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            s.bind((host, 0))
            return s.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis – polski asystent głosowy")
    parser.add_argument("--browser", action="store_true", help="otwórz interfejs w przeglądarce zamiast okna")
    parser.add_argument("--no-voice", action="store_true", help="bez mikrofonu i dźwięku (tylko komendy tekstowe)")
    parser.add_argument("--fullscreen", action="store_true", help="okno na pełnym ekranie (np. Raspberry Pi)")
    parser.add_argument("--port", type=int, default=8765, help="port interfejsu (domyślnie 8765)")
    parser.add_argument("--debug", action="store_true", help="szczegółowe logi i narzędzia deweloperskie w oknie")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # polskie znaki w konsoli Windows
    _setup_logging(args.debug)
    log = logging.getLogger("jarvis")

    # importy po konfiguracji logów (moduły logują już przy imporcie)
    from jarvis.app import JarvisApp
    from jarvis.ui.window import run_window
    from jarvis.web.server import WebServer, create_app

    app = JarvisApp(voice=not args.no_voice)
    host = "127.0.0.1"
    server = WebServer(create_app(app), host, _free_port(host, args.port))
    server.start()
    app.start()
    log.info("Interfejs: %s", server.url)

    try:
        fullscreen = args.fullscreen or app.settings.get().ui.fullscreen
        if args.browser or not run_window(server.url, app.bus, fullscreen=fullscreen, debug=args.debug):
            webbrowser.open(server.url)
            log.info("Ctrl+C kończy działanie")
            while True:
                time.sleep(1)  # (Event.wait bez limitu nie reaguje na Ctrl+C w Windows)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Zamykanie…")
        app.shutdown()
        server.stop()


if __name__ == "__main__":
    main()
