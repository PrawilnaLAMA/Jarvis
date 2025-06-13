import subprocess
from core.utils import is_similar

class TrainCommand:
    def __init__(self):
        pass

    def execute(self, message):
        words = message.split()
        for word in words:
            if is_similar(word.lower(), "pociąg", threshold=0.7):
                result = subprocess.run(["python", "pociag.py"], capture_output=True, text=True)
                output = result.stdout.strip()
                return "Następny pociąg: " + output
        return None
