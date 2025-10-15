import pandas as pd
from datetime import datetime
from core.separation_from_context import SeparationFromContext
from core.utils import is_similar
class TrainCommand:
    def __init__(self, data_path="trains/"):
        """
        Inicjalizacja klasy z ścieżką do danych GTFS
        """
        self.data_path = data_path
        pd.set_option('display.max_columns', None)
        self.load_data()
        self.stations = self.load_station_names()
    
    def load_data(self):
        """
        Wczytanie wszystkich potrzebnych plików GTFS
        """
        try:
            self.stop_times = pd.read_csv(f"{self.data_path}stop_times.txt")
            self.stops = pd.read_csv(f"{self.data_path}stops.txt")
            self.trips = pd.read_csv(f"{self.data_path}trips.txt")
            self.calendar = pd.read_csv(f"{self.data_path}calendar.txt")
        except FileNotFoundError as e:
            print(f"Błąd podczas wczytywania plików: {e}")
            raise
    
    def load_station_names(self):
        """
        Wczytuje listę dostępnych stacji kolejowych z danych GTFS.
        """
        try:
            # Pobierz unikalne nazwy stacji i posortuj je
            stations = self.stops['stop_name'].unique().tolist()
            
            # Konwertuj do wielkich liter i usuń duplikaty spowodowane różnicami w wielkości liter
            stations_upper = list(set([station.upper() for station in stations]))
            
            # Posortuj alfabetycznie dla spójności
            stations_upper.sort()
            
            return stations_upper
            
        except Exception as e:
            print(f"Błąd podczas wczytywania stacji: {e}")
            return []
    
    def extract_stations(self, command: str) -> tuple:
        """
        Wyodrębnia stację początkową (po 'z') i docelową (po 'do') z komendy użytkownika.

        Args:
            command (str): np. "Znajdź pociąg z Wałbrzycha Szczawienka do Wrocławia Głównego"

        Returns:
            tuple: Krotka (stacja_początkowa, stacja_docelowa) gdzie każda to string lub pusty string
        """
        if not self.stations:
            return "", ""
        
        # Prosta implementacja bez AI - można ją później zastąpić AI
        command_lower = command.lower()
        
        # Znajdź pozycje " z " i " do "
        z_index = command_lower.find(" z ")
        do_index = command_lower.find(" do ")
        
        start_station = ""
        end_station = ""
        
        # Ekstrakcja stacji początkowej
        if z_index != -1:
            if do_index != -1:
                # Jest zarówno " z " jak i " do "
                start_text = command[z_index + 3:do_index].strip()
            else:
                # Jest tylko " z "
                start_text = command[z_index + 3:].strip()
            
            # Znajdź najlepsze dopasowanie stacji
            start_station = self.find_best_station_match(start_text)
        
        # Ekstrakcja stacji docelowej
        if do_index != -1:
            end_text = command[do_index + 4:].strip()
            # Usuń ewentualne dodatkowe słowa po stacji
            end_text = end_text.split(',')[0].split(' ')[0]  # Prosta heurystyka
            end_station = self.find_best_station_match(end_text)
        
        return start_station, end_station
    
    def find_best_station_match(self, text: str) -> str:
        """
        Znajduje najlepsze dopasowanie stacji dla podanego tekstu.
        """
        if not text:
            return ""
        
        text_upper = text.upper()
        
        # Szukamy dokładnego dopasowania
        for station in self.stations:
            if text_upper in station or station in text_upper:
                return station
        
        # Szukamy częściowego dopasowania
        for station in self.stations:
            station_words = station.split()
            text_words = text_upper.split()
            
            # Sprawdź czy wszystkie słowa z tekstu są w nazwie stacji
            if all(any(word in station_word for station_word in station_words) for word in text_words):
                return station
        
        return ""
    
    def get_stop_ids(self, stop_name):
        """
        Pobranie listy ID dla podanej nazwy przystanku
        """
        if self.stops.empty:
            return []
        
        # Zbieramy pasujące wiersze w liście
        matching_rows = []
        
        # Przechodzimy przez wszystkie wiersze w stops
        for index, row in self.stops.iterrows():
            if is_similar(row['stop_name'].upper(), stop_name.upper()):
                matching_rows.append(row)
        
        # Tworzymy DataFrame tylko jeśli znaleźliśmy jakieś stacje
        if matching_rows:
            filtered_stops = pd.DataFrame(matching_rows)
            # print("filtered: ", filtered_stops)
            # print("stop name: ", stop_name)
            return filtered_stops['stop_id'].tolist()
        else:
            return []
        
    def get_departures_for_stop(self, stop_name):
        """
        Pobranie listy odjazdów dla podanego przystanku
        Zwraca listę krotek (trip_id, departure_time)
        """
        stop_ids = self.get_stop_ids(stop_name)
        
        if not stop_ids:
            raise ValueError(f"Nie znaleziono przystanku: {stop_name}")
        
        # Filtruj czasy odjazdów dla przystanku
        filtered_stop_times = pd.concat(
            [self.stop_times[self.stop_times['stop_id'] == id] for id in stop_ids],
            ignore_index=True
        )
        
        # Pobierz trip_id
        trip_ids = filtered_stop_times['trip_id'].tolist()
        
        # Filtruj trip_id według aktualnego dnia
        filtered_trips = self.filter_trips_by_current_day(trip_ids)
        filtered_trip_ids = filtered_trips['trip_id'].tolist()
        
        # Filtruj czasy odjazdów tylko dla aktywnych trip_id
        filtered_stop_times = filtered_stop_times[
            filtered_stop_times['trip_id'].isin(filtered_trip_ids)
        ]
        
        # Przygotuj listę czasów odjazdów
        departure_times = filtered_stop_times['departure_time'].tolist()
        departure_times = [
            "00:" + time_str[3:] if time_str.startswith("24:") else time_str
            for time_str in departure_times
        ]
        
        trip_ids_filtered = filtered_stop_times['trip_id'].tolist()
        
        return list(zip(trip_ids_filtered, departure_times))
    
    def filter_trips_by_current_day(self, trip_ids):
        """
        Filtrowanie tripów według aktualnego dnia tygodnia i daty
        """
        # Znajdź service_id dla podanych trip_ids
        filtered_trips = self.trips[self.trips['trip_id'].isin(trip_ids)]
        service_ids = filtered_trips['service_id'].unique().tolist()
        
        # Filtruj calendar według dnia tygodnia
        week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today_weekday = datetime.now().weekday()
        
        calendar_filtered = self.calendar[
            (self.calendar['service_id'].isin(service_ids)) &
            (self.calendar[week[today_weekday]] == 1)
        ]
        
        # Filtruj według daty obowiązywania
        today = datetime.now().date()
        calendar_filtered = calendar_filtered[
            (calendar_filtered['start_date'].apply(lambda x: datetime.strptime(str(x), "%Y%m%d").date()) <= today) &
            (calendar_filtered['end_date'].apply(lambda x: datetime.strptime(str(x), "%Y%m%d").date()) >= today)
        ]
        
        # Zwróć trip_id dla aktywnych service_id
        active_service_ids = calendar_filtered['service_id'].tolist()
        return self.trips[self.trips['service_id'].isin(active_service_ids)]
    
    def find_next_departure(self, from_stop="Wałbrzych Szczawienko", to_stop="Wrocław Główny"):
        """
        Znajdź najbliższy odjazd z przystanku początkowego do docelowego
        """
        try:
            # Pobierz odjazdy z przystanku początkowego
            from_departures = self.get_departures_for_stop(from_stop)
            # Pobierz odjazdy z przystanku docelowego
            to_departures = self.get_departures_for_stop(to_stop)
            
            # Stwórz słowniki dla łatwiejszego wyszukiwania
            from_dict = {trip_id: time for trip_id, time in from_departures}
            to_dict = {trip_id: time for trip_id, time in to_departures}
            
            # Znajdź wspólne trip_id gdzie czas odjazdu < czas przyjazdu
            valid_departures = []
            current_time = datetime.now().time()
            
            for trip_id, departure_time in from_departures:
                if trip_id in to_dict:
                    if departure_time < to_dict[trip_id]:
                        departure_time_obj = datetime.strptime(departure_time, "%H:%M:%S").time()
                        if departure_time_obj > current_time:
                            valid_departures.append(departure_time[:5])  # Format HH:MM
            
            if not valid_departures:
                return f"Brak połączeń z {from_stop} do {to_stop} po aktualnej godzinie"
            
            return sorted(valid_departures)[0]
            
        except ValueError as e:
            return f"Błąd: {e}"
        except Exception as e:
            return f"Wystąpił nieoczekiwany błąd: {e}"
    
    def __call__(self, command: str):
        """
        Umożliwia wywołanie klasy jak funkcji z komendą tekstową.
        Parsuje komendę i zwraca najbliższy odjazd.
        
        Args:
            command (str): Komenda użytkownika, np. "pociąg z Wałbrzycha do Wrocławia"
        
        Returns:
            str: Najbliższy odjazd lub komunikat błędu
        """
        # Wyodrębnij stacje z komendy
        ai = SeparationFromContext()
        start_station, end_station = ai.extract_stations(command)
        print(f"Wyodrębnione stacje: {start_station} -> {end_station}")
        # Użyj domyślnych wartości jeśli któreś stacje nie zostały znalezione
        if not start_station:
            start_station = "Wałbrzych Szczawienko"
        if not end_station:
            end_station = "Wrocław Główny"
        # print(start_station, end_station)
        # Znajdź najbliższy odjazd
        return self.find_next_departure(start_station, end_station)


# Przykład użycia:
if __name__ == "__main__":
    # Inicjalizacja harmonogramu
    schedule = TrainCommand()
    
    # Użycie poprzez __call__ z komendą tekstową
    result1 = schedule("pociąg z Wałbrzycha Szczawienko do Wrocławia Głównego")
    print(f"Wynik 1: {result1}")
    
    result2 = schedule("znajdź pociąg do Wrocławia")
    print(f"Wynik 2: {result2}")
    
    result3 = schedule("kiedy odjeżdża pociąg z Jeleniej Góry")
    print(f"Wynik 3: {result3}")
    
    # Tradycyjne użycie
    next_departure = schedule.find_next_departure()
    print(f"Najbliższy odjazd: {next_departure}")
    
    # Niestandardowa trasa
    custom_departure = schedule.find_next_departure("Wałbrzych Miasto", "Wrocław Główny")
    print(f"Najbliższy odjazd z Wałbrzycha Miasto: {custom_departure}")