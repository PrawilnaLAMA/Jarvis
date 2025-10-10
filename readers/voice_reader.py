import speech_recognition as sr
import logging
import time
import threading
from gtts import gTTS
from playsound import playsound
import os
from core.utils import is_similar

class VoiceReader:
    def __init__(self, command_handler):
        self.recognizer = sr.Recognizer()
        self.command_handler = command_handler
        self.calibrated = False
    
    def say(self, text):
        def speak():
            try:
                tts = gTTS(text=text, lang='pl')
                audio_file = "temp_audio.mp3"
                tts.save(audio_file)
                playsound(audio_file)
                os.remove(audio_file)  # Usuń plik po odtworzeniu
            except Exception as e:
                logging.error(f"Błąd w say: {e}")

        threading.Thread(target=speak).start()

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
                    audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
                    command = self.recognizer.recognize_google(audio, language="pl-PL")
                    logging.info(f"Rozpoznano komendę: {command}")
                    print(f"Rozpoznano komendę: {command}")
                    return command
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    self.say("Błąd połączenia z usługą rozpoznawania mowy.")
                    continue
                except sr.WaitTimeoutError:
                    continue

    def execute(self):
        while True:
            try:
                komenda_glosowa = self.listen_microphone()
                if komenda_glosowa:
                    words = komenda_glosowa.split()
                    # Znajdź słowo podobne do 'jarvis'
                    jarvis_word = None
                    for word in words:
                        if is_similar(word.lower(), "jarvis", threshold=0.5):
                            jarvis_word = word
                            break
                    if jarvis_word:
                        # Usuń znalezione słowo z komendy
                        filtered_words = [w for w in words if w != jarvis_word]
                        filtered_command = " ".join(filtered_words)
                        response = self.command_handler.handle_command(filtered_command)
                        if response:
                            self.say(response)
                            logging.info(f"Odpowiedź na komendę: {response}")
            except Exception as e:
                logging.error(f"Error during voice command execution: {e}")
                self.say("Wystąpił błąd. Spróbuj ponownie.")
