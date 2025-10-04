import os
import requests
import re
from dotenv import load_dotenv
from utils import is_similar
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"

class SeparationFromContext:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.url = GROQ_URL
        self.model = GROQ_MODEL

    def ask_ai(self, prompt: str, system_message: str = None) -> str:
        if system_message is None:
            system_message = "Odpowiadaj zawsze po polsku. Bądź bardzo zwięzły – maksymalnie 2-3 zdania. bądź uprzejmy i pomocny."
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 80,
        }
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=30)
            result = response.json()
            if 'choices' in result:
                return result['choices'][0]['message']['content']
            else:
                return "błędna odpowiedź modelu"
        except Exception as e:
            print(f"Błąd API: {e}")
            return "błędna odpowiedź modelu"

    def extract_song_title(self, command: str) -> str:
        """
        Wyodrębnia tytuł piosenki z komendy użytkownika.
        
        Args:
            command (str): Komenda użytkownika, np. "puść na youtube hello"
            
        Returns:
            str: Wyodrębniony tytuł piosenki
        """
        system_message = """Jesteś asystentem do ekstrakcji tytułów piosenek. 
        Twoim zadaniem jest wyodrębnienie TYLKO tytułu piosenki z komendy użytkownika.
        Zwróć wyłącznie tytuł piosenki, bez żadnych dodatkowych słów, znaków interpunkcyjnych ani komentarzy.
        Jeśli nie możesz znaleźć tytułu, zwróć pusty string. Zamiast spacji w odpowiedzi używaj podkreślenia (_)."""
        
        prompt = f"""Wyodrębnij tytuł piosenki z tej komendy: "{command}"
        
        Przykłady:
        - "puść na youtube hello" -> "hello"
        - "włącz despacito" -> "despacito" 
        - "zagraj shape of you" -> "shape_of_you"
        - "odtwórz bohemian rhapsody" -> "bohemian_rhapsody"

        Tytuł:"""
        
        return self.ask_ai(prompt, system_message).strip()


    def load_channel_names(self, env_path=".env"):
        """
        Ładuje listę osób z pliku .env (te, które zaczynają się od CHANNEL_).
        """
        load_dotenv(env_path)  # załadowanie zmiennych z pliku .env
        names = []

        for key in os.environ.keys():
            if key.startswith("CHANNEL_"):
                # wyciągamy nazwę po CHANNEL_
                match = re.match(r"CHANNEL_([A-ZĄĆĘŁŃÓŚŹŻ]+)", key)
                if match:
                    names.append(match.group(1))
        return names

    def extract_recipient(self, command: str, env_path=".env", threshold=0.6) -> str:
        """
        Wyodrębnia odbiorcę wiadomości z komendy użytkownika.

        Args:
            command (str): np. "Napisz piotrkowi, że nie mogę grać"
            env_path (str): ścieżka do pliku .env
            threshold (float): minimalny próg pewności dopasowania (0-1)

        Returns:
            str: Nazwa odbiorcy (np. "PIOTREK"), albo pusty string jeśli brak pewności.
        """
        recipients = self.load_channel_names(env_path)

        best_match = ""
        best_score = 0.0

        for recipient in recipients:
            # sprawdzamy każdy wyraz z komendy, czy pasuje do imienia
            for word in command.split():
                if is_similar(word.lower().strip(",.!?"), recipient.lower(), threshold):
                    return recipient

        return ""
