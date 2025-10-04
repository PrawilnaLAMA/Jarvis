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

    def listen_microphone(self):
        while True:
            with sr.Microphone() as source:
                print("Nasłuchuję... Powiedz coś!")
                try:
                    audio = self.recognizer.listen(source)
                    command = self.recognizer.recognize_google(audio, language="pl-PL")
                    logging.info(f"Rozpoznano komendę: {command}")
                    print(f"Rozpoznano komendę: {command}")
                    return command
                except sr.UnknownValueError:
                    continue  # Kontynuuj nasłuchiwanie
                except sr.RequestError as e:
                    self.say("Błąd połączenia z usługą rozpoznawania mowy.")
                    continue  # Kontynuuj nasłuchiwanie

    def execute(self):
        while True:
            try:
                komenda_glosowa = self.listen_microphone()
                if komenda_glosowa:
                    words = komenda_glosowa.split()
                    # Znajdź słowo podobne do 'jarvis'
                    jarvis_word = None
                    for word in words:
                        if is_similar(word.lower(), "jarvis", threshold=0.7):
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
