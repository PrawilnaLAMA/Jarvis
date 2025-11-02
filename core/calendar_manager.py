import json
import os
import uuid
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from tkinter import messagebox

class CalendarManager:
    """Prosty manager wydarzeń zapisanych w pliku JSON.

    Event schema (example):
    - recurring block:
      {
        "id": "uuid",
        "type": "work",
        "days": ["Monday", "Friday"],
        "start": "09:00",
        "end": "17:00",
        "desc": "Praca"
      }
    - single appointment:
      {
        "id": "uuid",
        "type": "appointment",
        "date": "2025-11-04",
        "start": "15:00",
        "end": "16:00",
        "desc": "Fryzjer"
      }
    """

    def __init__(self, path: str = "calendar_app/events.json"):
        self.path = path
        self.events: List[Dict[str, Any]] = []
        self.load_events()

    def load_events(self):
        if not os.path.exists(self.path):
            self.events = []
            return
        with open(self.path, "r", encoding="utf-8") as f:
            try:
                self.events = json.load(f)
            except json.JSONDecodeError:
                self.events = []

    def save_events(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)

    def add_event(self, event_info: dict = None) -> str:
        """Tworzy i dodaje nowe wydarzenie, zwraca id. Ustawia reminded=True domyślnie."""
        
        # Jeśli przekazano event_info z extract_event_info, użyj tych danych
        if event_info is not None:
            evt = {
                "type": event_info.get("type", "").strip() or "appointment",
                "date": event_info.get("date", "").strip() or None,
                "days": [],  # Dni powtarzania - puste dla wydarzeń z mowy
                "start": event_info.get("start", "").strip() or None,
                "desc": event_info.get("desc", "").strip() or "",
                "reminded": True
            }
        else:
            # Tworzenie słownika wydarzenia z danych z interfejsu (oryginalna logika)
            evt = {
                "type": self.type_var.get().strip() or "appointment",
                "date": self.date_var.get().strip() or None,
                "days": [d.strip() for d in self.days_var.get().split(',') if d.strip()],
                "start": self.start_var.get().strip() or None,
                "desc": self.desc_var.get().strip() or "",
                "reminded": True
            }
        
        
        # Walidacja - musi być data lub dni
        if evt["date"] is None and not evt["days"]:
            messagebox.showerror("Błąd", "Podaj datę lub dni powtarzania")
            return ""
        
        # Nadanie ID
        if "id" not in evt:
            evt["id"] = str(uuid.uuid4())
        
        # Dodanie do listy i zapis
        self.events.append(evt)
        self.save_events()
        
        return evt["id"]

    def remove_event(self, event_id: str) -> bool:
        before = len(self.events)
        self.events = [e for e in self.events if e.get("id") != event_id]
        changed = len(self.events) != before
        if changed:
            self.save_events()
        return changed

    def update_event(self, event_id: str, new_data: Dict[str, Any]) -> bool:
        for i, e in enumerate(self.events):
            if e.get("id") == event_id:
                self.events[i].update(new_data)
                self.save_events()
                return True
        return False

    def list_events(self) -> List[Dict[str, Any]]:
        return self.events

    def get_events_on_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Return events applicable on a specific date (recurring + exact date)."""
        results: List[Dict[str, Any]] = []
        weekday_name = target_date.strftime("%A")  # e.g., 'Monday'
        for e in self.events:
            # recurring by weekday
            if e.get("days"):
                if weekday_name in e.get("days", []):
                    results.append(e)
                    continue
            # exact date
            if e.get("date"):
                try:
                    d = datetime.strptime(e.get("date"), "%Y-%m-%d").date()
                    
                    if d == target_date:
                        results.append(e)
                except Exception:
                    continue
        return results

    def get_upcoming_events(self, from_dt: datetime, to_dt: datetime) -> List[Dict[str, Any]]:
        """Find events that start between from_dt and to_dt (inclusive of recurring events matching day).
        Only return events with reminded=True, and set reminded=False after reminder.
        """
        self.load_events()
        results: List[Dict[str, Any]] = []
        date_cursor = from_dt.date()
        updated = False
        while date_cursor <= to_dt.date():
            day_events = self.get_events_on_date(date_cursor)
            for e in day_events:
                # compute start datetime
                if e.get("start"):
                    try:
                        hh, mm = [int(p) for p in e.get("start").split(":")]
                        start_dt = datetime.combine(date_cursor, time(hh, mm))
                        if from_dt <= start_dt <= to_dt:
                            # Only remind if reminded is True (default True)
                            if e.get("reminded", True):
                                results.append({"event": e, "start_dt": start_dt})
                                e["reminded"] = False
                                updated = True
                    except Exception:
                        continue
            date_cursor = date_cursor + timedelta(days=1)
        if updated:
            self.save_events()
        return results


# quick smoke test when run directly
if __name__ == "__main__":
    cm = CalendarManager()
    print("Loaded events:", cm.list_events())
