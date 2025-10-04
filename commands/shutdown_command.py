import os
from core.utils import is_similar

class ShutdownCommand:
    def __call__(self, message):

        os.system("shutdown /s /t 1")
        return "Wyłączam komputer."

