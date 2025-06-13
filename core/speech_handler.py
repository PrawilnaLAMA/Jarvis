from gtts import gTTS
from playsound import playsound
import os
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
