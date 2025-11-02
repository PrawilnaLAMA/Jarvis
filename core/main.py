import sys
import os
import configparser
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import discord_config

from core.command_handler import CommandHandler
from readers.voice_reader import VoiceReader
import threading
import time
from core.utils import say
import logging
from command_classifier import CommandClassifier
from core.calendar_manager import CalendarManager


def process_output(output):
    """Centralized processing of command outputs."""
    if output:
        say(output)
        logging.info(f"Processed output: {output}")


class VoiceAssistant:
    def __init__(self, model_path='command_classifier.pkl'):
        self.classifier = CommandClassifier.load_model(model_path)
        print("Asystent głosowy załadowany!")
    
    def process_command(self, text):
        """Przetwarzanie komendy tekstowej"""
        print(f"Otrzymano komendę: '{text}'")
        
        result = self.classifier.predict(text)
        
        print(f"Rozpoznano komendę: {result['command']}")
        print(f"Pewność: {result['confidence']:.3f}")
        
        # Wykonanie akcji na podstawie komendy
        self.execute_command(result['command'], text, result['confidence'])
        
        return result


def main():
    # Load configuration
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), '../config.txt'))

    # Example usage of configuration
    DISCORD_CHANNEL_ID = discord_config["discord_channel_id"]
    print(f"Using Discord Channel ID: {DISCORD_CHANNEL_ID}")
    from core.utils import start_in_thread
    from readers.reminder_reader import ReminderReader
    from readers.discord_reader import DiscordReader

    def say_async(msg: str):
        threading.Thread(target=say, args=(msg,), daemon=True).start()

    voice_reader = VoiceReader(CommandHandler())
    reminder_reader = ReminderReader(callback=say_async, check_interval=5, reminder_minutes=60)
    discord_reader = DiscordReader()

    # Uruchomienie ReminderReader w osobnym wątku przez utils.py
    start_in_thread(reminder_reader, method_name='start')
    start_in_thread(voice_reader, method_name='execute')
    start_in_thread(discord_reader, method_name='monitor_channels')

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
