import speech_recognition as sr
import logging
import time
import threading
from core.utils import say
from core.utils import is_similar

class VoiceReader:
    def __init__(self, command_handler):
        self.recognizer = sr.Recognizer()
        self.command_handler = command_handler
        self.calibrated = False
    
    # Usunięto lokalną funkcję say, używaj say z utils

    def calibrate_microphone(self):
        """Kalibracja mikrofonu - wykonaj raz na początku"""
        with sr.Microphone() as source:
            print("Kalibracja mikrofonu... Proszę zachować ciszę przez 2 sekundy.")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            print("Kalibracja zakończona!")
            self.calibrated = True

    def listen_microphone(self):
        while True:
            with sr.Microphone() as source:
                if not self.calibrated:
                    self.calibrate_microphone()
                
                print("Nasłuchuję... Powiedz coś!")
                try:
                    audio = self.recognizer.listen(source)
                    command = self.recognizer.recognize_google(audio, language="pl-PL")
                    logging.info(f"Rozpoznano komendę: {command}")
                    print(f"Rozpoznano komendę: {command}")
                    return command
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    print("Błąd połączenia z usługą rozpoznawania mowy.")
                    continue
                except sr.WaitTimeoutError:
                    continue

    def execute(self):
        while True:
            try:
                komenda_glosowa = self.listen_microphone()
                if komenda_glosowa:
                    # Znajdź pozycję pierwszego wystąpienia "gutek"
                    jarvis_index = komenda_glosowa.lower().find("gutek")
                    if jarvis_index != -1:
                        # Usuń wszystko przed pierwszym "gutek" i weź resztę tekstu
                        command_after_jarvis = komenda_glosowa[jarvis_index:]
                        
                        # Podziel na komendy używając "gutek" jako separatora
                        filtered_commands = [cmd.strip() for cmd in command_after_jarvis.split('Jarvis') if cmd.strip()]
                        
                        for command in filtered_commands:
                            response = self.command_handler.handle_command(command)
                            if response:
                                say(response)
                                logging.info(f"Odpowiedź na komendę: {response}")
            except Exception as e:
                logging.error(f"Error during voice command execution: {e}")
                say("Wystąpił błąd. Spróbuj ponownie.")