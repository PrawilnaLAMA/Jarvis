from core.utils import is_similar
import webbrowser

class GoogleCommand:
    def execute(self, message):
        words = message.split()
        for word in words:
            if is_similar(word.lower(), "google", threshold=0.7):
                query = message.split(word)[-1].strip()
                webbrowser.open(f"https://www.google.com/search?q={query}&oq={query}&aqs=chrome")
                return f"Otwieram Google i wyszukuję: {query}"
        return None
