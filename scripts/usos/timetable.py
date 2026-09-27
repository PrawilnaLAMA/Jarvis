"""Wypisuje plan zajęć z USOS na najbliższe dni.

Uruchomienie: py scripts/usos/timetable.py [RRRR-MM-DD] [liczba_dni]
(wymaga: pip install requests-oauthlib oraz tokenów z get_tokens.py w .env)
"""

import sys
from datetime import date, datetime

import requests
from common import BASE_URL, require
from requests_oauthlib import OAuth1Session

FIELDS = "start_time|end_time|name|type|building_name|room_number|course_id|classtype_name"


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    usos = OAuth1Session(
        require("USOS_CONSUMER_KEY"),
        client_secret=require("USOS_CONSUMER_SECRET"),
        resource_owner_key=require("USOS_ACCESS_TOKEN"),
        resource_owner_secret=require("USOS_ACCESS_TOKEN_SECRET"),
    )
    try:
        response = usos.get(BASE_URL + "services/tt/student", params={"start": start, "days": days, "fields": FIELDS})
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        sys.exit(f"❌ Błąd HTTP: {err}")

    classes = sorted(response.json(), key=lambda x: x.get("start_time", ""))
    print(f"📅 ZAJĘCIA od {start} ({days} dni)")
    print("=" * 50)
    if not classes:
        print("🎉 Brak zajęć!")
        return

    now = datetime.now()
    for i, c in enumerate(classes, 1):
        name = c.get("name", {}).get("pl", "Brak nazwy")
        kind = c.get("classtype_name", {}).get("pl", c.get("type", "Nieznany"))
        start_s, end_s = c.get("start_time", ""), c.get("end_time", "")
        print(f"{i}. 🎓 {name}")
        print(f"   📚 Typ: {kind}")
        print(f"   ⏰ {start_s or '?'} – {end_s.split(' ')[-1] if end_s else '?'}")
        print(f"   📍 {c.get('building_name', {}).get('pl', 'Nie podano')}, sala {c.get('room_number', '?')}")
        if start_s and end_s:
            s = datetime.strptime(start_s, "%Y-%m-%d %H:%M:%S")
            e = datetime.strptime(end_s, "%Y-%m-%d %H:%M:%S")
            print("   ✅ ZAKOŃCZONE" if e < now else "   🔷 NADCHODZĄCE" if s > now else "   🔴 TRWAJĄ TERAZ")
        print()


if __name__ == "__main__":
    main()
