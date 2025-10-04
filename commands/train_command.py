import subprocess
from core.utils import is_similar

class TrainCommand:
    def __init__(self):
        pass

    def __call__(self, message):
        result = subprocess.run(["python", "pociag.py"], capture_output=True, text=True)
        output = result.stdout.strip()
        return "Następny pociąg: " + output
