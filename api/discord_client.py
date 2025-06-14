import requests
from core.config import discord_config

class DiscordClient:
    def __init__(self):
        self.token = discord_config["jarvis_token"]
        self.headers = {'authorization': f'{self.token}'}

    def get_messages(self, channel_id):
        url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def send_message(self, channel_id, content):
        url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
        payload = {'content': content}
        response = requests.post(url, headers=self.headers, data=payload)
        response.raise_for_status()
        return response.json()
