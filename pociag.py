import pandas as pd
from datetime import datetime
#opcja zeby wyswietlalo wszystkie kolumny
pd.set_option('display.max_columns', None)

#otwieranie plików
#czasy odjazdów pociągów
file_path = "pociagi/stop_times.txt" 
try:
    stop_times = pd.read_csv(file_path)
except FileNotFoundError:
    print(f"Plik {file_path} nie został znaleziony.")
#informacje o przystankach
file_path = "pociagi/stops.txt" 
try:
    stops = pd.read_csv(file_path)
except FileNotFoundError:
    print(f"Plik {file_path} nie został znaleziony.")
#informacje o podróżach
file_path = "pociagi/trips.txt" 
try:
    trips = pd.read_csv(file_path)
except FileNotFoundError:
    print(f"Plik {file_path} nie został znaleziony.")
#informacje o przejazdach w dni tygodnia
file_path = "pociagi/calendar.txt" 
try:
    calendar = pd.read_csv(file_path)
except FileNotFoundError:
    print(f"Plik {file_path} nie został znaleziony.")

#wałbrzych miasto

filtered_stops_wm = stops[(stops['stop_name'] == ("Wałbrzych Miasto"))]
stop_id_list_wm = filtered_stops_wm['stop_id'].tolist()

filtered_stop_times_wm = pd.concat(
    [stop_times[stop_times['stop_id'] == id] for id in stop_id_list_wm],
    ignore_index=True
)

trip_id_list_wm = filtered_stop_times_wm['trip_id'].tolist()

filtered_trip_id_wm = pd.concat(
    [trips[trips['trip_id'] == id] for id in trip_id_list_wm],
    ignore_index=True
)


service_id_list_wm = filtered_trip_id_wm['service_id'].tolist()

week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

calendar_days = pd.concat(
    [calendar[calendar["service_id"] == id] for id in service_id_list_wm],
    ignore_index=True
)

calendar_days = pd.concat(
    [calendar_days[calendar_days[week[datetime.now().weekday()]] == 1]],
    ignore_index=True
)

calendar_days = calendar_days[
    (calendar_days["start_date"].apply(lambda x: datetime.strptime(str(x), "%Y%m%d").date()) <= datetime.now().date()) &
    (calendar_days["end_date"].apply(lambda x: datetime.strptime(str(x), "%Y%m%d").date()) >= datetime.now().date())
].reset_index(drop=True)


filtered_service_id_list_wm = calendar_days['service_id'].tolist()

filtered_trips_wm = pd.concat(
    [trips[trips["service_id"] == id] for id in filtered_service_id_list_wm],
    ignore_index=True
)

trip_id_list_wm = filtered_trips_wm['trip_id'].tolist()

filtered_stop_times_wm = pd.concat(
    [filtered_stop_times_wm[filtered_stop_times_wm["trip_id"] == id] for id in trip_id_list_wm],
    ignore_index=True
)

stop_departure_time_list_wm = filtered_stop_times_wm['departure_time'].tolist()
stop_departure_time_list_wm = [
    "00:" + time_str[3:]  # Zmieniamy "24:" na "00:"
    if time_str.startswith("24:") else time_str  # Jeśli godzina zaczyna się od "24:", zamień, w przeciwnym razie zachowaj oryginalny czas
    for time_str in stop_departure_time_list_wm
]

# print(sorted(stop_departure_time_list_wm))

trip_and_departure_list_wm = list(zip(trip_id_list_wm, stop_departure_time_list_wm))
#wrocław główny

filtered_stops_wg = stops[(stops['stop_name'] == ("Wrocław Główny"))]
stop_id_list_wg = filtered_stops_wg['stop_id'].tolist()

filtered_stop_times_wg = pd.concat(
    [stop_times[stop_times['stop_id'] == id] for id in stop_id_list_wg],
    ignore_index=True
)
stop_departure_time_list_wg = filtered_stop_times_wg['departure_time'].tolist()
stop_departure_time_list_wg = [
    "00:" + time_str[3:]
    if time_str.startswith("24:") else time_str  
    for time_str in stop_departure_time_list_wg
]
trip_id_list_wg = filtered_stop_times_wg['trip_id'].tolist()



trip_and_departure_list_wg = list(zip(trip_id_list_wg, stop_departure_time_list_wg))

#odjazdy z wałbrzych miasto do wrocław główny
x = 0
arrival_times = []
for trip_and_departure_pair_wn in trip_and_departure_list_wm:
    for trip_and_departure_pair_wg in trip_and_departure_list_wg:
        if trip_and_departure_pair_wn[0] == trip_and_departure_pair_wg[0]:
            if trip_and_departure_pair_wn[1] < trip_and_departure_pair_wg[1]:
                x+=1
                if datetime.strptime(trip_and_departure_pair_wn[1], "%H:%M:%S").time() > datetime.now().time():
                    arrival_times.append(trip_and_departure_pair_wn[1][:5])
    

print(sorted(arrival_times)[0])
