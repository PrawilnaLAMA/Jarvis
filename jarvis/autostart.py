"""Uruchamianie Jarvisa razem z Windowsem – wpis „Jarvis” w HKCU\\...\\Run.

Wpis uruchamia `jarvis.pyw` przez pythonw (bez okna konsoli) i widać go w Menedżerze zadań →
Aplikacje autostartu. Rejestr jest jedynym źródłem prawdy (nic w settings.json), więc wyłączenie
wpisu gdziekolwiek indziej nie rozjedzie się z ustawieniami.
"""

import contextlib
import logging
import sys
from pathlib import Path

from jarvis import paths

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Jarvis"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    # pythonw tego samego interpretera, który ma zainstalowane pakiety Jarvisa
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{paths.ROOT / "jarvis.pyw"}"'


def _current() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, NAME)[0]
    except FileNotFoundError:
        return None


def is_enabled() -> bool:
    return supported() and _current() is not None


def set_enabled(enabled: bool) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, NAME)
    log.info("Autostart z Windowsem: %s", "włączony" if enabled else "wyłączony")


def refresh() -> None:
    """Po przeniesieniu katalogu albo zmianie Pythona wpis wskazywałby stare ścieżki – poprawiamy go."""
    if not supported():
        return
    try:
        current = _current()
        if current is not None and current != command():
            set_enabled(True)
    except OSError:
        log.warning("Nie udało się odświeżyć wpisu autostartu", exc_info=True)


def status() -> dict[str, bool]:
    return {"supported": supported(), "enabled": is_enabled()}
