from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import webbrowser
import pyautogui as py
import time
import speech_recognition as sr
import pyttsx3 as tts
import subprocess as sp
import requests
import json
import urllib.request
import re
from datetime import datetime
from selenium.webdriver.chrome.options import Options
import keyboard
import os
import subprocess
import numpy as np
import sys
from dotenv import load_dotenv

load_dotenv()

user_token = os.getenv("USER_TOKEN")
jarvis_token = os.getenv("JARVIS_TOKEN")

user_header = {'authorization':f'{user_token}'}
jarvis_header = {'authorization':f'{jarvis_token}'}

arguments = sys.argv[1:]  # sys.argv[0] to nazwa programu, więc pomijamy ją
print("Odebrane argumenty:", arguments)

# from openai import OpenAI
# import os
# from dotenv import load_dotenv

# load_dotenv()
# client = OpenAI(
#     api_key = os.getenv("jarvisKey")
# )

# completion = client.chat.completions.create(
#     model = "gpt-3.5-turbo-instruct",
#     messages = [
#         {"role": "system", "content": "Czy trawa jest zielona?"},
#         {"role": "user", "content": "powiedz cos o trawach w ameryce"},
#     ]
# )

# print(completion.choices[0].message)


def replace_line(file_name, line_num, text):
    lines = open(file_name, 'r').readlines()
    lines[line_num] = text + '\n'
    out = open(file_name, 'w')
    out.writelines(lines)
    out.close()

    

engine = tts.init()
engine.setProperty("rate", 140)
poprzedni = [0,0,0,0,0,0,0]
def mow(text):
    if 'http' not in text:
        engine.say(text)
        engine.runAndWait()
    else:
        engine.say('wysłał link')
        engine.runAndWait()

def get_audio_level(audio_data):
    # Przekształcenie surowych danych audio na tablicę numeryczną
    audio_array = np.frombuffer(audio_data.frame_data, dtype=np.int16)
    # Obliczanie poziomu dźwięku jako średnia absolutna wartość
    return np.mean(np.abs(audio_array))


def getText():
    # print("Naciśnij przycisk 'f8', aby włączyć jarvisa")
    # keyboard.wait('f8')
    
    print("Rozpoczęto nagrywanie...")
    with sr.Microphone(device_index=0) as source:
        r = sr.Recognizer()
        r.dynamic_energy_threshold = False
        r.energy_threshold = 400
        try:
            audio = r.listen(source)
            text = r.recognize_google(audio, language='pl-PL')
            if text != "":
                return text
            return 0
        except sr.WaitTimeoutError:
            print("Przerwano nagrywanie")
            return 0
        except sr.UnknownValueError:
            print("Nie rozpoznano mowy")
            return 0
        except sr.RequestError as e:
            print("Błąd serwera; {0}".format(e))
            return 0

def do_kogos(txt, number, who = 'brak'):
    
    if who != 'brak':
        if who in txt:
            txt = txt.replace(who, '')
            payload = {'content': str(txt)}
            rq = requests.post('https://canary.discord.com/api/v9/channels/' + number + '/messages', data=payload, headers=user_header)

            if rq.status_code == 200 or rq.status_code == 201:
                print("Wiadomość wysłana pomyślnie.")
            else:
                print("Błąd wysyłania wiadomości:", rq.status_code)
            mow("Wiadomość została wysłana")
    else:
        payload = {'content': str(txt)}
        rq = requests.post('https://canary.discord.com/api/v9/channels/' + number + '/messages', data=payload, headers=user_header)
        mow("Wiadomość została wysłana")


def dodaj(x, y):
    return x + y

def odejmij(x, y):
    return x - y

def pomnoz(x, y):
    return x * y

def podziel(x, y):
    return x / y

czytanieCheck = True

def jarvis_commands(txt):
    if not txt == 0:
        txt = txt.lower()
        txt = txt.replace(' znak zapytania', '?')
        txt = txt.replace('znak zapytania', '?')
        txt = txt.replace(' wielokropek', '...')
        txt = txt.replace(' kropka ', '.')
        txt = txt.replace('dawid', 'jarvis')
        txt = txt.replace('serwis', 'jarvis')
        print(str(txt))
        if "jarvis stop" in txt:
            return
        # if "wyłącz czytanie wiadomości" in txt:
        #     replace_line('config.txt', 0, 'False')
        #     mow("czytanie wiadomości - wyłączone")
        # if "włącz czytanie wiadomości" in txt:
        #     replace_line('config.txt', 0, 'True')
        #     mow("czytanie wiadomości - włączone")
        if "jarvis włącz kalkulator" in txt:
            sp.call("calc")
        # if "włącz discord" in txt or "włącz discorda" in txt or "włączyć discorda" in txt:
        #     sp.call("C://Users//Lemon//AppData//Local//Discord//app-1.0.9005//Discord.exe")
        # if "włącz rocket league" in txt:
        #     sp.call("C://steam//steamapps/common//rocketleague//Binaries//Win64//RocketLeague.exe")
        
        if "jarvis włącz youtube" in txt or "jarvis otwórz youtube" in txt:
            webbrowser.open("https://www.youtube.com")
        if "jarvis" in txt and ("znajdź" in txt or "puść" in txt or "włącz" in txt) and ("youtubie" in txt or "youtube" in txt):
            if "youtube" in txt:
                txt = txt.split("youtube")
            if "youtubie" in txt:
                txt = txt.split("youtubie")
            
            txt = txt[1] 
            txt = txt.replace(' ', '_')
            txt = txt.replace('ż', 'z')
            txt = txt.replace('ź', 'z')
            txt = txt.replace('ą', 'a')
            txt = txt.replace('ę', 'e')
            txt = txt.replace('ś', 's')
            txt = txt.replace('ć', 'c')
            txt = txt.replace('ó', 'o')

            print(txt)
            html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + txt)
            video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
            print("https://www.youtube.com/watch?v=" + video_ids[0])
            webbrowser.open("https://www.youtube.com/watch?v=" + video_ids[0])
            
        if "jarvis otwórz google" in txt:
            webbrowser.open("https://www.google.com/") 
            mow("Otwieram")
        if "znajdź w internecie" in txt or "wyszukaj w internecie" in txt or "znajdź na internecie" in txt:
            if "znajdź w internecie" in txt:
                txt = txt.split("znajdź w internecie")  
            if "wyszukaj w internecie" in txt:
                txt = txt.split("wyszukaj w internecie")
            if "znajdź na internecie" in txt:
                txt = txt.split("znajdź na internecie")
            txt = txt[1]
            webbrowser.open("https://www.google.com/search?q=" + str(txt) + "&oq=" + str(txt) + "&aqs=chrome")

        if "jarvis wyślij wiadomość" in txt:
            if "jarvis wyślij wiadomość" in txt:
                txt = txt.split("wyślij wiadomość")  
            txt = txt[1]
            do_kogos(txt, '843175716870029363', 'do piotrka')
            do_kogos(txt, '645228974552776730', 'do martina')
            do_kogos(txt, '592310033329422346', 'do bartka')
            do_kogos(txt, '603692596279377941', 'do adriana')
            do_kogos(txt, '783059152158720020', 'do bąbel')
            do_kogos(txt, '692013621001060415', 'do adama')
            do_kogos(txt, '755468294844317725', 'do denisa')
            do_kogos(txt, '9982248515191439972', 'do pauliny')
            do_kogos(txt, '1152758021252984852', 'do natalii')
            do_kogos(txt, '1152758021252984852', 'do natalki')
        if "jarvis włącz streama" in txt or "jarvis wyłącz streama" in txt or "jarvis włącz streema" in txt or "jarvis wyłącz streema" in txt or "jarvis włącz stream" in txt or "jarvis wyłącz stream" in txt or "jarvis wyłącz strima" in txt or "jarvis włącz strima" in txt:
            py.press('num2')
        
        if "jarvis odpisz" in txt:
            txt = txt.split("jarvis odpisz") 
            txt = txt[1]
            lines = open('config.txt', 'r').readlines()
            lines[1] = lines[1].replace('\n', '')
            do_kogos(txt, str(lines[1]))

        if "jarvis napisz" in txt:
            txt = txt.split("jarvis napisz") 
            txt = txt[1]
            txt = txt.replace('ż', 'z')
            txt = txt.replace('ź', 'z')
            txt = txt.replace('ą', 'a')
            txt = txt.replace('ę', 'e')
            txt = txt.replace('ś', 's')
            txt = txt.replace('ć', 'c')
            txt = txt.replace('ó', 'o')
            py.write(txt, interval=0.01)

        if "jarvis wyłącz się" in txt:
            mow("Naura")
            return
        if "jarvis oblicz" in txt:
            txt = txt.split("jarvis oblicz") 
            txt = txt[1]
            txt = txt.replace(' kropka ', '.')
            numbers = [str(s) for s in txt.split()]
            
            for i in range(len(numbers)):
                if numbers[i] == "minus" or numbers[i] == "-":
                    numbers[i+1] = odejmij(float(numbers[i-1]), float(numbers[i+1]))
                if numbers[i] == "plus" or numbers[i] == "+":
                    numbers[i+1] = dodaj(float(numbers[i-1]), float(numbers[i+1]))
                if numbers[i] == "razy" or numbers[i] == "x":
                    numbers[i+1] = pomnoz(float(numbers[i-1]), float(numbers[i+1]))
                if numbers[i] == "na":
                    if numbers[i-1] != "podzielić" or numbers[i] == "/":
                        numbers[i+1] = podziel(float(numbers[i-1]), float(numbers[i+1]))
                    else:
                        numbers[i+1] = podziel(float(numbers[i-2]), float(numbers[i+1]))
        if "jarvis która godzina" in txt:
            current_time = datetime.now()
            print("Aktualna godzina:", current_time.strftime("%H:%M:%S"))    
            mow(str(current_time.strftime("%H:%M")))
        if "jarvis" in txt and "pociąg" in txt:
            result = subprocess.run(["python", "pociag.py"], capture_output=True, text=True)
            output = result.stdout
            print("Nastepny pociag: " + output)
            mow("Następny pociąg: " + output)

if len(arguments) > 0:
    jarvis_commands(arguments[0])
else:
    while True:
        txt = getText()
        jarvis_commands(txt)
        if not txt:
            print("Nie udało się rozpoznać...")

def retrieve_messages(req, numer):     
    jsonn = json.loads(req.text)   
    if poprzedni[numer] != jsonn[0]['content']:
        author = jsonn[0]['author']['username']
        if author != 'PrawilnaLAMA':
            if author == 'Kawa':
                author = 'Adam'
            if author == 'bOOmkotzniszczenia9907':
                author = 'Bartek'
            if author == 'Foxyg3n':
                author = 'Piotrek'
            if author == 'Sharyxxx':
                author = 'Martin'
            if author == 'Nishii':
                author = 'Natalka'
            print(author, jsonn[0]['content'], '\n')    
            mow(author)
            mow(jsonn[0]['content']) 
            return jsonn[0]['content']

def check_retrieve_messages(req, numer):        
    jsonn = json.loads(req.text)
    if poprzedni[numer] != jsonn[0]['content']:
        if jsonn[0]['author']['username'] != 'PrawilnaLAMA':
            return jsonn[0]['content']

