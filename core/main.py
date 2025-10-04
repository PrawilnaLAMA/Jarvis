import sys
import os
import configparser
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import discord_config


from api.discord_client import DiscordClient
from core.command_handler import CommandHandler
from readers.voice_reader import VoiceReader
from readers.discord_reader import DiscordReader
import threading
import time
from gtts import gTTS
from playsound import playsound
import logging


def speak(text):
    try:
        tts = gTTS(text=text, lang='pl')
        audio_file = "temp_audio.mp3"
        tts.save(audio_file)
        playsound(audio_file)
        os.remove(audio_file)  # Usuń plik po odtworzeniu
    except Exception as e:
        logging.error(f"Błąd w speak: {e}")

def process_output(output):
    """Centralized processing of command outputs."""
    if output:
        speak(output)
        logging.info(f"Processed output: {output}")

def main():
    # Load configuration
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), '../config.txt'))

    # Example usage of configuration
    DISCORD_CHANNEL_ID = discord_config["discord_channel_id"]
    print(f"Using Discord Channel ID: {DISCORD_CHANNEL_ID}")
    discord_client = DiscordClient()
    command_handler = CommandHandler(discord_client)
    voice_reader = VoiceReader(command_handler)
    discord_reader = DiscordReader(discord_client, command_handler, DISCORD_CHANNEL_ID)

    # Uruchomienie VoiceCommand w osobnym wątku
    threading.Thread(target=voice_reader.execute, daemon=True).start()

    # Uruchomienie DiscordReader w osobnym wątku
    threading.Thread(target=discord_reader.read_messages, daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
