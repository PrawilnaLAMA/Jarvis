import requests
from difflib import SequenceMatcher
import logging
import re
from core.config import discord_config

# Use the imported configuration
CHANNEL_IDS = discord_config["channel_ids"]
USER_TOKEN = discord_config["user_token"]
HEADERS = {'authorization': f'{USER_TOKEN}'}

class DiscordMessageCommand:
    def __init__(self):
        pass

    def execute(self, message):
        match = re.search(r"^wyślij wiadomość\s+do\s+(\S+)\s+(.*)$", message.lower())

        if not match:
            return None
        
        print("test0")

        recipient = match.group(1)  
        content = match.group(2)  
        
        if recipient:
            print("test1")
            channel_id = None
            for key in CHANNEL_IDS.keys():
                if SequenceMatcher(None, recipient.upper(), key).ratio() >= 0.7:
                    channel_id = CHANNEL_IDS.get(key)
                    break
            print("channel_id:", channel_id)
            if not channel_id:
                return f"Nie znaleziono kanału dla odbiorcy: {recipient}"
            payload = {'content': content}
            print("payload:", payload)
            # Dodaj obsługę odpowiedzi i błędów:
            response = requests.post(
                f'https://discord.com/api/v9/channels/{channel_id}/messages', 
                json=payload,  # użyj json zamiast data
                headers=HEADERS
            )

            print(f"Status: {response.status_code}")
            print(f"Odpowiedź: {response.text}")

            if response.status_code != 200:
                print(f"Błąd: {response.status_code} - {response.text}")

        return None
