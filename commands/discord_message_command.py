import requests
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher
import logging

load_dotenv()

USER_TOKEN = os.getenv("USER_TOKEN")
HEADERS = {'authorization': f'{USER_TOKEN}'}

# Configure logging to avoid spam
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Function to dynamically create CHANNEL_IDS from .env file
CHANNEL_IDS = {
    key.split('_')[1].lower(): os.getenv(key)
    for key in os.environ.keys()
    if key.startswith("CHANNEL_")
}

def is_similar(word, target, threshold=0.7):
    """Check if the similarity between two words exceeds the threshold."""
    return SequenceMatcher(None, word, target).ratio() >= threshold

class DiscordMessageCommand:
    def __init__(self):
        pass

    def execute(self, message):
        words = message.split()
        if any(is_similar(word, "wyślij wiadomość") for word in words):
            # print("DEBUG: Wywołano komendę wysyłania wiadomości.")
            recipient = None
            matched_word = None  # Zapisanie dopasowanego słowa
            for word in words:
                matches = [key for key in CHANNEL_IDS.keys() if is_similar(word.lower(), key)]
                if matches:
                    recipient = matches[0]
                    matched_word = word  # Zapisanie dopasowanego słowa
                    break
            if recipient:
                # Wyciągnięcie treści wiadomości po nazwie odbiorcy z użyciem dopasowanego słowa
                split_message = message.split(f"do {matched_word}", 1)
                # print(f"DEBUG: wiadomosc: {message}")
                # print(f"DEBUG: split_message: {split_message}")
                # print(f"DEBUG: recipient: do {matched_word}")
                if len(split_message) > 1:
                    content = split_message[1].strip()
                else:
                    return "Nie można wyodrębnić treści wiadomości."
                channel_id = CHANNEL_IDS[recipient]
                payload = {'content': content}
                try:
                    response = requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', data=payload, headers=HEADERS)
                    response.raise_for_status()
                except requests.exceptions.HTTPError as e:
                    if response.status_code == 401:
                        logger.error("401 Client Error: Unauthorized for URL %s", f'https://discord.com/api/v9/channels/{channel_id}/messages')
                    else:
                        logger.error("HTTP Error: %s", e)
                except Exception as e:
                    logger.error("An unexpected error occurred: %s", e)
                else:
                    if response.status_code in [200, 201]:
                        return f"Wiadomość do {recipient} wysłana pomyślnie."
                    else:
                        return f"Błąd wysyłania wiadomości do {recipient}: {response.status_code}"
            else:
                return "Nie znaleziono odbiorcy wiadomości."
        return None
