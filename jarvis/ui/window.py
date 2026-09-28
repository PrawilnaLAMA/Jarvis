"""Natywne okno z interfejsem (pywebview: WebView2 na Windows, WebKitGTK na Raspberry Pi)."""

import logging

from jarvis.events import Event, EventBus

log = logging.getLogger(__name__)


def run_window(url: str, bus: EventBus, fullscreen: bool = False, debug: bool = False) -> bool:
    """Blokuje do zamknięcia okna. Zwraca False, gdy pywebview jest niedostępne."""
    try:
        import webview
    except ImportError:
        log.warning("pywebview niedostępne – otwieram interfejs w przeglądarce")
        return False

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
