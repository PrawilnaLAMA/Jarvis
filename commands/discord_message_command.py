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
        recipients = ai.extract_recipients(message)

        if not recipients:
            return "Nie znaleziono żadnego odbiorcy w treści wiadomości."

        # Wygeneruj jedną, krótką wiadomość do wysłania
        content = generator.generate_message(message)
        payload = {'content': content}

        sent = []
        errors = []

        for name in recipients:
            channel_id = None
            # exact match (case-insensitive) against CHANNEL_IDS keys
            for key, val in CHANNEL_IDS.items():
                if key.lower() == name.lower():
                    channel_id = val
                    break

            # fuzzy fallback
            if not channel_id:
                for key, val in CHANNEL_IDS.items():
                    if SequenceMatcher(None, name.lower(), key.lower()).ratio() >= 0.7:
                        channel_id = val
                        break

            if not channel_id:
                errors.append((name, 'Nie znaleziono kanału'))
                continue

            try:
                response = requests.post(
                    f'https://discord.com/api/v9/channels/{channel_id}/messages',
                    json=payload,
                    headers=HEADERS,
                    timeout=15
                )
                if response.status_code in (200, 201):
                    sent.append((name, channel_id))
                else:
                    errors.append((name, f'Status {response.status_code}: {response.text}'))
            except Exception as e:
                errors.append((name, str(e)))

        if sent and not errors:
            targets = ", ".join([s[0] for s in sent])
            print(f"Wiadomość wysłana do: {targets}")
            print(f"Wiadomość: {content}")
            return f"Wiadomość wysłana do: {targets}"
        else:
            msg = ""
            if sent:
                msg += "Wysłano do: " + ", ".join([s[0] for s in sent]) + ". "
            if errors:
                msg += "Błędy: " + "; ".join([f'{e[0]} -> {e[1]}' for e in errors])
            return msg
