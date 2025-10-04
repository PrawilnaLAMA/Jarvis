import os
import requests
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"

class GenerateMessages:
	def __init__(self):
		self.api_key = GROQ_API_KEY
		self.url = GROQ_URL
		self.model = GROQ_MODEL

	def ask_ai(self, prompt: str, system_message: str = None) -> str:
		if system_message is None:
			system_message = (
				"Jesteś asystentem do generowania krótkich, naturalnych wiadomości na Discordzie. "
				"Nie dodawaj żadnych wyjaśnień, nie powtarzaj polecenia, nie dodawaj emotek ani podpisu. "
				"Odpowiadaj zawsze po polsku."
				"""Przykłady:
				- napisz do piotrka, że nie mam czasu grać w lola  -> Sorka. Aktualnie nie mam czasu.
                - odpisz Natalii, że mogę zagrać grę w lola -> Mogę zagrać gierkę
                - zapytaj natana czy coś aktualnie robi -> robisz coś aktualnie?
                - przywitaj się i zapytaj czy Kawa ma trochę czasu -> siema, masz czas?
				"""
			)
		headers = {
			"Authorization": f"Bearer {self.api_key}",
			"Content-Type": "application/json"
		}
		data = {
			"model": self.model,
			"messages": [
				{"role": "system", "content": system_message},
				{"role": "user", "content": prompt}
			],
			"temperature": 0.5,
			"max_tokens": 60,
		}
		try:
			response = requests.post(self.url, headers=headers, json=data, timeout=30)
			result = response.json()
			if 'choices' in result:
				return result['choices'][0]['message']['content'].strip()
			else:
				return "błąd odpowiedzi modelu"
		except Exception as e:
			print(f"Błąd API: {e}")
			return "błąd odpowiedzi modelu"

	def generate_message(self, prompt: str) -> str:
		"""
		Generuje krótką, naturalną wiadomość na podstawie prompta użytkownika.
		"""
		return self.ask_ai(prompt)

# Przykład użycia
if __name__ == "__main__":
	generator = GenerateMessages()
	test_prompts = [
		"napisz do piotrka, że nie mam czasu grać w lola",
		"odpisz Natalii, że mogę zagrać grę w lola",
		"zapytaj natana czy coś aktualnie robi",
		"przywitaj się i zapytaj czy Kawa ma trochę czasu"
	]
	print("=== TEST GENEROWANIA WIADOMOŚCI ===")
	for prompt in test_prompts:
		msg = generator.generate_message(prompt)
		print(f"Prompt: '{prompt}' -> Wiadomość: '{msg}'")
