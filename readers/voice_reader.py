import speech_recognition as sr
import logging
import threading
import queue
from core.utils import say

class VoiceReader:
    def __init__(self, command_handler):
        self.recognizer = sr.Recognizer()
        self.command_handler = command_handler
        self.calibrated = False
        self.audio_queue = queue.Queue()
        self.listening_active = False
        self.listener_thread = None

    def calibrate_microphone(self):
        """Kalibracja mikrofonu - wykonaj raz na początku"""
        with sr.Microphone() as source:
            print("Kalibracja mikrofonu... Proszę zachować ciszę przez 2 sekundy.")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
            print("Kalibracja zakończona!")
            self.calibrated = True

    def continuous_listening_worker(self):
        """Wątek ciągłego nasłuchiwania w tle"""
        with sr.Microphone() as source:
            if not self.calibrated:
                self.calibrate_microphone()
            
            while self.listening_active:
                try:
                    print("Nasłuchuję... Powiedz coś!")
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=10)
                    # Dodaj audio do kolejki do przetworzenia
                    self.audio_queue.put(audio)
                except sr.WaitTimeoutError:
                    # Timeout jest normalny - po prostu kontynuuj nasłuchiwanie
                    continue
                except Exception as e:
                    logging.error(f"Błąd podczas nasłuchiwania: {e}")
                    continue

    def start_listening(self):
        """Rozpocznij ciągłe nasłuchiwanie w osobnym wątku"""
        if not self.listening_active:
            self.listening_active = True
            self.listener_thread = threading.Thread(target=self.continuous_listening_worker, daemon=True)
            self.listener_thread.start()
            print("Rozpoczęto ciągłe nasłuchiwanie w tle...")

    def stop_listening(self):
        """Zatrzymaj ciągłe nasłuchiwanie"""
        self.listening_active = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        print("Zatrzymano nasłuchiwanie.")

    def process_audio(self, audio):
        """Przetwórz audio i zwróć rozpoznany tekst"""
        try:
            command = self.recognizer.recognize_google(audio, language="pl-PL")
            logging.info(f"Rozpoznano komendę: {command}")
            print(f"Rozpoznano komendę: {command}")
            return command
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print("Błąd połączenia z usługą rozpoznawania mowy.")
            logging.error(f"Request error: {e}")
            return None

    def execute(self):
        # Rozpocznij ciągłe nasłuchiwanie w tle
        self.start_listening()
        
        try:
            while True:
                try:
                    # Pobierz audio z kolejki (blokuj z timeoutem)
                    audio = self.audio_queue.get(timeout=1)
                    
                    # Przetwórz audio w głównym wątku
                    komenda_glosowa = self.process_audio(audio)
                    
                    if komenda_glosowa:
                        # Znajdź pozycję pierwszego wystąpienia "Jarvis"
                        jarvis_index = komenda_glosowa.lower().find("jarvis")
                        if jarvis_index != -1:
                            # Usuń wszystko przed pierwszym "Jarvis" i weź resztę tekstu
                            command_after_jarvis = komenda_glosowa[jarvis_index:]
                            
                            # Podziel na komendy używając "Jarvis" jako separatora
                            filtered_commands = [cmd.strip() for cmd in command_after_jarvis.lower().split('jarvis') if cmd.strip()]
                            
                            for command in filtered_commands:
                                response = self.command_handler.handle_command(command)
                                if response:
                                    say(response)
                                    logging.info(f"Odpowiedź na komendę: {response}")
                    
                    # Oznacz zadanie jako zakończone
                    self.audio_queue.task_done()
                    
                except queue.Empty:
                    # Brak audio w kolejce - kontynuuj pętlę
                    continue
                except Exception as e:
                    logging.error(f"Error during voice command execution: {e}")
                    say("Wystąpił błąd. Spróbuj ponownie.")
        except KeyboardInterrupt:
            print("\nZatrzymywanie...")
            self.stop_listening()
        finally:
            self.stop_listening()