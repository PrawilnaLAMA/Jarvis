from datetime import datetime
from core.utils import is_similar

class TimeCommand:
    def __init__(self):
        pass

    def __call__(self, message):
        current_time = datetime.now().strftime("%H:%M")
        return f"Aktualna godzina: {current_time}"
