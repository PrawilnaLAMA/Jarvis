from gtts import gTTS
from playsound import playsound
import os
import logging

from difflib import SequenceMatcher
import re

def say(text):
    """
    Odtwarza tekst jako mowę (TTS) i usuwa plik po odtworzeniu.
    """
    try:
        print(f"Gutek mówi: {text}")
        text = re.sub(r'http\S+', 'link', text)
        tts = gTTS(text=text, lang='pl')
        audio_file = "temp_audio.mp3"
        tts.save(audio_file)
        playsound(audio_file)
        os.remove(audio_file)
    except Exception as e:
        logging.error(f"Błąd w say: {e}")

def is_similar(word, target, threshold=0.7):
    return SequenceMatcher(None, word, target).ratio() >= threshold

