import threading
import logging
from typing import Optional
from core.utils import say
from core.calendar_manager import CalendarManager



class ReminderReader:
    def __init__(self, check_interval: int = 60, reminder_minutes: int = 60, cm: Optional[CalendarManager] = None):
        self.cm = cm or CalendarManager()
        self.check_interval = check_interval
        self.reminder_minutes = reminder_minutes

    def start(self):
        """Run the reminder checking loop (to be called in a thread by utils)."""
        from datetime import datetime, timedelta
        while True:
            now = datetime.now()
            window_start = now
            window_end = now + timedelta(minutes=self.reminder_minutes)
            events = self.cm.get_upcoming_events(window_start, window_end)
            for item in events:
                e = item.get("event")
                start_dt = item.get("start_dt")
                desc = e.get("desc") or e.get("type") or "Wydarzenie"
                msg = f"Przypomnienie: {desc} o {start_dt.strftime('%H:%M')}"
                say(msg)
            threading.Event().wait(self.check_interval)

