import requests
from difflib import SequenceMatcher
import logging
import re
from core.config import discord_config
from core.separation_from_context import SeparationFromContext
from core.generate_messages import GenerateMessages
# Use the imported configuration
CHANNEL_IDS = discord_config["channel_ids"]
USER_TOKEN = discord_config["user_token"]
HEADERS = {'authorization': f'{USER_TOKEN}'}

class DiscordMessageCommand:
    def __call__(self, message):

        ai = SeparationFromContext()
        generator = GenerateMessages()
        recipient = ai.extract_recipient(message) 
        content = generator.generate_message(message)
        
        if recipient:
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
                json=payload,  
                headers=HEADERS
            )

            print(f"Status: {response.status_code}")
            print(f"Odpowiedź: {response.text}")

            if response.status_code != 200:
                print(f"Błąd: {response.status_code} - {response.text}")

        return None
