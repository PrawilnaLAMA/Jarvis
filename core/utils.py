from gtts import gTTS
from playsound import playsound
import os
import logging

from difflib import SequenceMatcher
import re
import pygame
import threading

def say(text):
    def play_audio():
        print(text)
        try:
            print("test0")
            tts = gTTS(text=text, lang='pl')
            audio_file = "temp_audio.mp3"
            tts.save(audio_file)
            print("test01")
            # Inicjalizuj pygame mixer
            pygame.mixer.init()
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            print("test02")
            # Czekaj aż skończy grać
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            print("test03")
            # Sprzątanie
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            os.remove(audio_file)
            
        except Exception as e:
            logging.error(f"Błąd w say: {e}")
            # Spróbuj zamknąć mixer nawet jeśli był błąd
            try:
                pygame.mixer.quit()
            except:
                pass

    # Uruchom w osobnym wątku
    threading.Thread(target=play_audio, daemon=True).start()

def is_similar(word, target, threshold=0.7):
    return SequenceMatcher(None, word, target).ratio() >= threshold

def start_in_thread(obj, method_name='run', daemon=True):
    """
    Uruchamia wskazaną metodę obiektu w nowym wątku.
    Domyślnie uruchamia metodę 'run', ale można podać inną nazwę.
    Przykład: start_in_thread(reader, 'start')
    """
    method = getattr(obj, method_name)
    thread = threading.Thread(target=method, daemon=daemon)
    thread.start()
    return thread

