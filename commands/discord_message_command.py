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
        
        recipient = match.group(1)  
        content = match.group(2)  
        
        if recipient:
            channel_id = None
            for key in CHANNEL_IDS.keys():
                if SequenceMatcher(None, recipient.upper(), key).ratio() >= 0.7:
                    channel_id = CHANNEL_IDS.get(key)
                    break
            if not channel_id:
                return f"Nie znaleziono kanału dla odbiorcy: {recipient}"
            payload = {'content': content}
            requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', data=payload, headers=HEADERS)

        return None
