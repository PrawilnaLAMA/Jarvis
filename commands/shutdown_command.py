import os
from core.utils import is_similar

class ShutdownCommand:
    def execute(self, message):
        # Komenda aktywuje się na frazę "wyłącz komputer"
        if is_similar(message.lower(), "wyłącz komputer", threshold=0.8):
            # Wyłączenie komputera (Windows)
            os.system("shutdown /s /t 1")
            return "Wyłączam komputer."
        return None
