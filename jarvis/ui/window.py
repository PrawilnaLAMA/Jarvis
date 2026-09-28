"""Natywne okno z interfejsem (pywebview: WebView2 na Windows, WebKitGTK na Raspberry Pi).

Na Windowsie domyślnie jako kulka na pulpicie (ui/desktop.py); pełny ekran i inne systemy – zwykłe okno.
"""

import logging
import sys
import threading

from jarvis import paths
from jarvis.events import Event, EventBus
from jarvis.settings import SettingsStore

log = logging.getLogger(__name__)


def run_window(url: str, bus: EventBus, settings: SettingsStore, fullscreen: bool = False, debug: bool = False) -> bool:
    """Blokuje do zamknięcia okna. Zwraca False, gdy pywebview jest niedostępne."""
    try:
        import webview
    except ImportError:
        log.warning("pywebview niedostępne – otwieram interfejs w przeglądarce")
        return False

    if sys.platform == "win32" and not fullscreen and settings.get().ui.desktop_orb:
        _desktop_window(webview, url, bus)
    else:
        window = webview.create_window(
            "Jarvis",
            url,
            width=1180,
            height=760,
            min_size=(640, 420),
            fullscreen=fullscreen,
            background_color="#05070d",
        )

        def bring_to_front(event: Event) -> None:
            # np. „otwórz kalendarz” głosem, gdy okno jest zminimalizowane lub pod innymi
            try:
                window.restore()
                window.on_top = True
                window.on_top = False
            except Exception:
                log.debug("Nie udało się przywołać okna", exc_info=True)

        bus.subscribe(bring_to_front, {"ui.navigate", "ui.show"})

    try:
        webview.start(debug=debug)
    except Exception:
        log.exception("Nie udało się uruchomić okna pywebview")
        return False
    return True


def _desktop_window(webview, url: str, bus: EventBus) -> None:
    from jarvis.ui.desktop import DesktopWindow

    def in_background(fn) -> None:
        # rozwijanie trwa ułamek sekundy (animacja) – nie blokujemy wątku, który opublikował zdarzenie
        threading.Thread(target=fn, name="desktop", daemon=True).start()

    def on_menu(choice: str) -> None:
        if choice == "open":
            desk.expand()
        elif choice == "settings":
            bus.publish("ui.navigate", view="settings")
        elif choice == "quit":
            desk.quit()

    desk = DesktopWindow(paths.DATA_DIR / "window.json", on_menu)
    desk.create(webview, url)
    # „otwórz kalendarz” głosem albo drugie uruchomienie Jarvisa – kulka się rozwija
    bus.subscribe(lambda _: in_background(desk.expand), {"ui.navigate", "ui.show"})
