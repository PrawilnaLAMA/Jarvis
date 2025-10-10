import os
import requests
from dotenv import load_dotenv
import json
from datetime import datetime

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"

class AICommand:
    def __init__(self, user_id="default"):
        self.api_key = GROQ_API_KEY
        self.url = GROQ_URL
        self.model = GROQ_MODEL
        self.user_id = user_id
        # 🟡 ZMIANA: Ścieżka do pliku w folderze cache
        self.history_file = f"cache/conversation_history_{user_id}.json"
        
    def load_conversation_history(self):
        """Ładuje historię konwersacji z pliku"""
        try:
            # 🟡 ZMIANA: Utworzenie folderu cache jeśli nie istnieje
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    
    def save_conversation_history(self, history):
        """Zapisuje historię konwersacji do pliku"""
        try:
            # 🟡 ZMIANA: Utworzenie folderu cache jeśli nie istnieje
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            
            # Przycinanie historii do ostatnich 6 wiadomości (3 pary)
            trimmed_history = history[-6:]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(trimmed_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Błąd zapisu historii: {e}")
    
    def clear_conversation_history(self):
        """Czyści historię konwersacji"""
        try:
            if os.path.exists(self.history_file):
                os.remove(self.history_file)
            return "Historia konwersacji została wyczyszczona."
        except Exception as e:
            return f"Błąd czyszczenia historii: {e}"
    
    def ask_ai(self, prompt: str) -> str:
        # Załaduj istniejącą historię
        conversation_history = self.load_conversation_history()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Dodaj nową wiadomość użytkownika
        conversation_history.append({"role": "user", "content": prompt, "timestamp": str(datetime.now())})
        
        # Przygotuj wiadomości do wysłania
        messages = [
            {
                "role": "system", 
                "content": "Odpowiadaj zawsze po polsku. Bądź zwięzły (1-2 zdania). Pamiętaj kontekst poprzednich wiadomości."
            }
        ] + [{"role": msg["role"], "content": msg["content"]} for msg in conversation_history[-6:]]  # Ostatnie 3 pary
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 100,
        }
        
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=30)
            result = response.json()
            
            if 'choices' in result:
                ai_response = result['choices'][0]['message']['content']
                
                # Dodaj odpowiedź AI do historii
                conversation_history.append({"role": "assistant", "content": ai_response, "timestamp": str(datetime.now())})
                
                # Zapisz zaktualizowaną historię
                self.save_conversation_history(conversation_history)
                
                return ai_response
            else:
                return "Przepraszam, wystąpił błąd. Spróbuj ponownie."
                
        except Exception as e:
            print(f"Błąd API: {e}")
            return "Przepraszam, problem z połączeniem."

    def __call__(self, message: str) -> str:
        return self.ask_ai(message)