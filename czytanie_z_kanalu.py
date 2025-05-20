import requests
import json
import time
import pyttsx3 as tts
import subprocess
import os
import dotenv

dotenv.load_dotenv()
jarvis_token = os.getenv("JARVIS_TOKEN")

jarvis_header = {'authorization':f'{jarvis_token}'}
engine = tts.init()
engine.setProperty("rate", 200)

def mow(text):
    engine.say(text)
    engine.runAndWait()

def retrieve_messages(req):        
    jsonn = json.loads(req.text)
    if poprzedni != jsonn[0]['content']:
        if jsonn[0]['author']['username'] == 'prawilnalama':
            print(jsonn[0]['content'], '\n')
            return jsonn[0]['content']

def check_retrieve_messages(req):        
    jsonn = json.loads(req.text)
    if poprzedni != jsonn[0]['content']:
        if jsonn[0]['author']['username'] != 'Jarvis':
            return jsonn[0]['content']


poprzedni = ""

while True:
    req = requests.get(f'https://discord.com/api/v9/channels/1320353346925891628/messages', headers = jarvis_header)
    if check_retrieve_messages(req):   
        poprzedni = retrieve_messages(req)
        result = subprocess.run(["python", "jarvis.py", "jarvis " + poprzedni], capture_output=True, text=True)
        output = result.stdout
        print(output)
    time.sleep(0.5)

