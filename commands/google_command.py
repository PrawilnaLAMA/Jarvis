from core.utils import is_similar
import webbrowser
from core.separation_from_context import SeparationFromContext

class GoogleCommand:
    def __call__(self, message):
        ai = SeparationFromContext()
        query = ai.extract_search_query(message)
        print(f"Extracted query: {query}")
        webbrowser.open(f"https://www.google.com/search?q={query}&oq={query}&aqs=chrome")
        return f"Otwieram Google i wyszukuję: {query}"
