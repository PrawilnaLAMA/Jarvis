"""Jarvis bez okna konsoli – uruchamiany przez pythonw z jarvis.bat i z autostartu Windowsa.

Nie ma konsoli, więc błąd startu pokazujemy w okienku (szczegóły w data/jarvis.log).
Katalog roboczy bywa dowolny (autostart startuje w System32), dlatego sami dopisujemy ścieżkę projektu.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from jarvis.__main__ import main

    main()
except SystemExit:
    raise
except BaseException as exc:
    import logging

    logging.getLogger("jarvis").critical("Jarvis nie wystartował", exc_info=True)
    if sys.platform == "win32":
        import ctypes

        text = f"Jarvis nie wystartował:\n{exc}\n\nSzczegóły: data\\jarvis.log"
        ctypes.windll.user32.MessageBoxW(None, text, "Jarvis", 0x10)  # 0x10 = ikona błędu
    raise
