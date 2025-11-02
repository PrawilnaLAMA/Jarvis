import sys
import subprocess
import threading
import logging


class CalendarOpenCommand:
    def __init__(self, action: str):
        # track subprocess to avoid opening multiple windows
        self.proc = None
        self.action = action

    def __call__(self, action: str):
        """Open the calendar GUI as a separate process.

        Uses the current Python executable to run the package module `calendar_app.app`.
        """
        if self.action == "open":
            try:
                # If process exists and is running, bring user message instead
                if self.proc and self.proc.poll() is None:
                    return "Kalendarz jest już otwarty."

                # Start the GUI in a new process
                python = sys.executable or "python"
                # Use creationflags on Windows to detach window if desired (optional)
                self.proc = subprocess.Popen([python, "-m", "calendar_app.app"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Otwieram kalendarz."
            except Exception as e:
                logging.exception("Nie udało się otworzyć kalendarza")
                return "Nie udało się otworzyć kalendarza."
        elif self.action == "add":
            # Dodaj wydarzenie przez komendę (przykład: dodanie spotkania na dziś o 15:00)
            from core.calendar_manager import CalendarManager
            cm = CalendarManager()
            from core.separation_from_context import SeparationFromContext
            separator = SeparationFromContext()
            # Użyj argumentu przekazanego do __call__ jako komendy
            event_info = separator.extract_event_info(action)
            # Ustaw reminded na True
            event_info["reminded"] = True
            # Dodaj do kalendarza tylko jeśli jest data i typ
            if event_info.get("date") and event_info.get("type"):
                cm.add_event(event_info)
                return f"Dodano wydarzenie: {event_info.get('desc', 'bez opisu')} {event_info.get('date')} {event_info.get('start', '')}"
            else:
                return "Nie udało się rozpoznać informacji o wydarzeniu."
