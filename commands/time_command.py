from datetime import datetime
from core.utils import is_similar

class TimeCommand:
    def __init__(self):
        pass

    def execute(self, message):
        words = message.split()
        for word in words:
            if is_similar(word.lower(), "time", threshold=0.7):
                current_time = datetime.now().strftime("%H:%M")
                return f"Aktualna godzina: {current_time}"
        return None
