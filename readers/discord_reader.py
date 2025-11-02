import requests
import time
import logging
from core.config import discord_config
from core.utils import say

USER_TOKEN = discord_config["user_token"]
CHANNEL_IDS = discord_config["channel_ids"]
MY_ID = "453603943214350337"
HEADERS = {'authorization': f'{USER_TOKEN}'}

# Mapowanie kanałów na "autora" do wypowiadania
CHANNEL_AUTHOR_MAP = {v: k.capitalize() for k, v in CHANNEL_IDS.items()}

class DiscordReader:
    def __init__(self):
        # Przy starcie pobierz ostatnie ID wiadomości z każdego kanału
        self.last_message_ids = {}
        for channel_id in CHANNEL_IDS.values():
            msg = self.fetch_latest_message(channel_id)
            self.last_message_ids[channel_id] = msg['id'] if msg else None

    # Usunięto lokalną funkcję say, używaj say z utils

    def fetch_latest_message(self, channel_id):
        try:
            url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit=1"
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    return messages[0]
            else:
                logging.error(f"Błąd pobierania wiadomości z kanału {channel_id}: {response.status_code}")
        except Exception as e:
            logging.error(f"Błąd pobierania wiadomości: {e}")
        return None

    def monitor_channels(self):
        while True:
            for channel_id in CHANNEL_IDS.values():
                message = self.fetch_latest_message(channel_id)
                if message:
                    msg_id = message['id']
                    author_id = message['author']['id']
                    content = message['content']
                    author_name = CHANNEL_AUTHOR_MAP.get(channel_id, "Nieznany")
                    # Jeśli nowa wiadomość i nie jest od Ciebie
                    if msg_id != self.last_message_ids[channel_id] and author_id != MY_ID:
                        self.last_message_ids[channel_id] = msg_id
                        output = f"{author_name} powiedział: {content}"
                        print(output)
                        say(output)
            time.sleep(2)  # Odpytywanie co 2 sekundy
