import requests
from requests_oauthlib import OAuth1Session
from datetime import datetime, timedelta

# === KONFIGURACJA ===
BASE_URL = 'https://apps.usos-szkol.pwr.edu.pl/'
CONSUMER_KEY = 'HxRNj2XUDcpSjVTr8nVJ'
CONSUMER_SECRET = 'cfHysJwHkRmdvT37pbshApDdKA4e3wKubVksTt9Y'
ACCESS_TOKEN = 'H78nz5kk4eMtwZTyzJdj'
ACCESS_TOKEN_SECRET = '8aDqf2aTzteFZtCW4cDCRY2kbuxkyNFdWvey9wpD'

# === PRZYGOTOWANIE SESJI ===
usos = OAuth1Session(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=ACCESS_TOKEN,
    resource_owner_secret=ACCESS_TOKEN_SECRET
)

# === PARAMETRY ZAPYTANIA - DZISIAJ ===
endpoint = 'services/tt/student'
url = BASE_URL + endpoint

# Pobieramy tylko dzisiejsze zajęcia
dzisiaj = '2025-10-30'
params = {
    'start': dzisiaj,  # 👈 Dzisiejsza data
    'days': 7,         # 👈 Tylko jeden dzień
    'fields': 'start_time|end_time|name|type|building_name|room_number|course_id|classtype_name'
}

try:
    response = usos.get(url, params=params)
    response.raise_for_status()
    
    plan_zajec = response.json()
    
    print(f"📅 ZAJĘCIA NA DZISIAJ ({dzisiaj})")
    print("=" * 50)
    
    if len(plan_zajec) == 0:
        print("🎉 Brak zajęć na dzisiaj! Możesz odpocząć.")
    else:
        # Sortowanie zajęć według godziny rozpoczęcia
        plan_zajec.sort(key=lambda x: x.get('start_time', ''))
        
        print(f"Liczba zajęć: {len(plan_zajec)}\n")
        
        for i, zajecia in enumerate(plan_zajec, 1):
            nazwa = zajecia.get('name', {}).get('pl', 'Brak nazwy')
            typ_zajec = zajecia.get('classtype_name', {}).get('pl', zajecia.get('type', 'Nieznany'))
            start = zajecia.get('start_time', '')
            end = zajecia.get('end_time', '')
            
            # Formatowanie godziny
            godzina_start = start.split(' ')[1] if start else '?'
            godzina_koniec = end.split(' ')[1] if end else '?'
            
            budynek = zajecia.get('building_name', {}).get('pl', 'Nie podano')
            sala = zajecia.get('room_number', 'Nie podano')
            
            print(f"{i}. 🎓 {nazwa}")
            print(f"   📚 Typ: {typ_zajec}")
            print(f"   ⏰ Godziny: {godzina_start} - {godzina_koniec}")
            print(f"   📍 Miejsce: {budynek}, sala {sala}")
            
            # Sprawdzamy czy zajęcia już się zakończyły
            if end:
                end_time = datetime.strptime(end, '%Y-%m-%d %H:%M:%S')
                if end_time < datetime.now():
                    print("   ✅ ZAJĘCIA ZAKOŃCZONE")
                elif datetime.strptime(start, '%Y-%m-%d %H:%M:%S') > datetime.now():
                    print("   🔷 NADCHODZĄCE")
                else:
                    print("   🔴 TRWAJĄ TERAZ")
            
            print()

except requests.exceptions.HTTPError as err:
    print(f"❌ Błąd HTTP: {err}")
except Exception as err:
    print(f"❌ Inny błąd: {err}")