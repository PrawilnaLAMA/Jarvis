import os
import requests
from core.config import discord_config
from core.utils import is_similar

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"

class AICommand:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.url = GROQ_URL
        self.model = GROQ_MODEL

    def ask_ai(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Odpowiadaj zawsze po polsku. "
                            "Bądź bardzo zwięzły – maksymalnie 2-3 zdania."
                            " bądź uprzejmy i pomocny."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,      # niska kreatywność
            "max_tokens": 80,         # twardy limit ~60-70 słów
        }
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=30)
            result = response.json()
            if 'choices' in result:
                return result['choices'][0]['message']['content']
            else:
                return "błędna odpowiedź modelu"
        except Exception:
            return "błędna odpowiedź modelu"

    def execute(self, message: str) -> str:
        # Szukaj frazy "powiedz mi" na początku lub w środku wiadomości
        words = message.split()
        for i, word in enumerate(words):
            if is_similar(word.lower(), "powiedz", threshold=0.8) and i+1 < len(words) and is_similar(words[i+1].lower(), "mi", threshold=0.8):
                prompt = " ".join(words[i+2:]).strip()
                if prompt:
                    return self.ask_ai(prompt)
        return None
