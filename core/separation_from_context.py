import os
import requests
import re
from dotenv import load_dotenv
from utils import is_similar
import pandas as pd
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "moonshotai/kimi-k2-instruct-0905"

class SeparationFromContext:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.url = GROQ_URL
        self.model = GROQ_MODEL

    def ask_ai(self, prompt: str, system_message: str = None) -> str:
        if system_message is None:
            system_message = "Odpowiadaj zawsze po polsku. Bądź bardzo zwięzły – maksymalnie 2-3 zdania. bądź uprzejmy i pomocny."
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 80,
        }
        try:
            response = requests.post(self.url, headers=headers, json=data, timeout=30)
            result = response.json()
            if 'choices' in result:
                return result['choices'][0]['message']['content']
            else:
                return "błędna odpowiedź modelu"
        except Exception as e:
            print(f"Błąd API: {e}")
            return "błędna odpowiedź modelu"

    def extract_song_title(self, command: str) -> str:
        """
        Wyodrębnia tytuł piosenki z komendy użytkownika.
        
        Args:
            command (str): Komenda użytkownika, np. "puść na youtube hello"
            
        Returns:
            str: Wyodrębniony tytuł piosenki
        """
        system_message = """Jesteś asystentem do ekstrakcji tytułów piosenek. 
        Twoim zadaniem jest wyodrębnienie TYLKO tytułu piosenki z komendy użytkownika.
        Zwróć wyłącznie tytuł piosenki, bez żadnych dodatkowych słów, znaków interpunkcyjnych ani komentarzy.
        Jeśli nie możesz znaleźć tytułu, zwróć pusty string. Zamiast spacji w odpowiedzi używaj podkreślenia (_)."""
        
        prompt = f"""Wyodrębnij tytuł piosenki z tej komendy: "{command}"
        
        Przykłady:
        - "puść na youtube hello" -> "hello"
        - "włącz despacito" -> "despacito" 
        - "zagraj shape of you" -> "shape_of_you"
        - "odtwórz bohemian rhapsody" -> "bohemian_rhapsody"

        Tytuł:"""
        
        return self.ask_ai(prompt, system_message).strip()

    def extract_search_query(self, command: str) -> str:
        """
        Wyodrębnia zapytanie wyszukiwania z komendy użytkownika.
        
        Args:
            command (str): Komenda użytkownika, np. "wyszukaj informacje o Marsie"
            
        Returns:
            str: Wyodrębnione zapytanie wyszukiwania
        """
        system_message = """Jesteś asystentem do ekstrakcji zapytań wyszukiwania. 
        Twoim zadaniem jest wyodrębnienie TYLKO zapytania wyszukiwania z komendy użytkownika.
        Zwróć wyłącznie zapytanie wyszukiwania, bez żadnych dodatkowych słów, znaków interpunkcyjnych ani komentarzy.
        Jeśli nie możesz znaleźć zapytania, zwróć pusty string."""
        
        prompt = f"""Wyodrębnij zapytanie wyszukiwania z tej komendy: "{command}"
        
        Przykłady:
        - "wyszukaj informacje o Marsie" -> "informacje o Marsie"
        - "znajdź najlepsze restauracje w Krakowie" -> "najlepsze restauracje w Krakowie"
        - "szukaj jak upiec ciasto" -> "jak upiec ciasto"
        - "wyszukaj w internecie aktualne wiadomości" -> "aktualne wiadomości"
        - "znajdź definicję sztucznej inteligencji" -> "definicja sztucznej inteligencji"
        - "wyszukaj zdjęcia kotów" -> "zdjęcia kotów"

        Zapytanie wyszukiwania:"""
        
        return self.ask_ai(prompt, system_message).strip()

    def load_channel_names(self, env_path=".env"):
        """
        Ładuje listę osób z pliku .env (te, które zaczynają się od CHANNEL_).
        """
        load_dotenv(env_path)  # załadowanie zmiennych z pliku .env
        names = []

        for key in os.environ.keys():
            if key.startswith("CHANNEL_"):
                # wyciągamy nazwę po CHANNEL_
                match = re.match(r"CHANNEL_([A-ZĄĆĘŁŃÓŚŹŻ]+)", key)
                if match:
                    names.append(match.group(1))
        return names

    def extract_recipients(self, command: str, env_path=".env") -> list:
        """
        Wyodrębnia odbiorcę/odbiorców wiadomości z komendy użytkownika używając AI.
        Obsługuje przypadki z wieloma odbiorcami.

        Args:
            command (str): np. "Napisz piotrkowi i anii, że nie mogę grać"
            env_path (str): ścieżka do pliku .env

        Returns:
            list: Lista nazw odbiorców (np. ["PIOTREK", "ANIA"]), lub pusta lista jeśli brak
        """
        recipients = self.load_channel_names(env_path)
        
        if not recipients:
            return []
        
        system_message = """Jesteś asystentem do identyfikacji odbiorców wiadomości. 
        Twoim zadaniem jest znalezienie WSZYSTKICH osób, do których adresowana jest wiadomość.
        Z listy dostępnych osób wybierz TYLKO te, które są wyraźnie wymienione w komendzie.
        Jeśli wiadomość jest adresowana do więcej niż jednej osoby, zwróć wszystkie nazwy oddzielone przecinkami.
        Zwróć nazwy WIELKIMI LITERAMI tak jak na liście, bez żadnych dodatkowych słów, znaków interpunkcyjnych ani komentarzy.
        Jeśli nie możesz znaleźć żadnego odbiorcy, zwróć pusty string."""

        recipients_list = ", ".join(recipients)
        
        prompt = f"""Dostępne osoby: {recipients_list}

        Komenda: "{command}"

        Przykłady:
        - "powiedz piotrkowi że przyjdę później" -> "PIOTREK"
        - "napisz do anny i tomasza żeby przyszli" -> "ANNA,TOMASZ" 
        - "poinformuj wszystkich że spotkanie jest odwołane" -> ""
        - "wiadomość dla marka i kasi: nie ma mnie" -> "MAREK,KASIA"
        - "powiedz jej żeby zadzwoniła" -> ""

        Odbiorcy:"""
        
        result = self.ask_ai(prompt, system_message).strip()
        
        if result:
            found_recipients = []
            for name in result.split(','):
                name = name.strip().upper()
                if name in recipients:
                    found_recipients.append(name)
            
            if found_recipients:
                return found_recipients  # Zwracamy listę, nie stringa
        
        return []  # Zwracamy pustą listę zamiast pustego stringa
    def extract_stations(self, command: str, env_path=".env") -> tuple:
        """
        Wyodrębnia stację początkową (po 'z') i docelową (po 'do') z komendy użytkownika używając AI.

        Args:
            command (str): np. "Znajdź pociąg z Wałbrzycha Szczawienka do Wrocławia Głównego"
            env_path (str): ścieżka do pliku .env

        Returns:
            tuple: Krotka (stacja_początkowa, stacja_docelowa) gdzie każda to string lub pusty string
        """
        # Wczytaj dostępne stacje z danych GTFS
        stations = self.load_station_names(env_path)
        
        if not stations:
            return "", ""
        
        system_message = """Jesteś asystentem do identyfikacji stacji kolejowych w komendach tekstowych.
        Twoim zadaniem jest znalezienie stacji początkowej (po słowie "z") i docelowej (po słowie "do") w komendzie użytkownika.
        
        ZASADY:
        1. Stacja początkowa znajduje się ZAWSZE po słowie "z" w dopełniaczu (np. "z Wałbrzycha", "z Jeleniej Góry")
        2. Stacja docelowa znajduje się ZAWSZE po słowie "do" w dopełniaczu (np. "do Wrocławia", "do Warszawy")
        3. Jeśli brakuje którejkolwiek ze stacji, zwróć pusty string w jej miejscu
        4. Dopasuj nazwy do poprawnej formy z listy dostępnych stacji
        
        Zwróć wynik w formacie: "STACJA_POCZĄTKOWA,STACJA_DOCELOWA"
        Używaj WIELKICH LITER i tylko prawidłowych nazw stacji z listy.
        Jeśli nie ma stacji początkowej, zwróć ",STACJA_DOCELOWA"
        Jeśli nie ma stacji docelowej, zwróć "STACJA_POCZĄTKOWA,"
        Jeśli nie ma żadnej stacji, zwróć pusty string."""

        stations_list = ", ".join(stations)
        
        prompt = f"""Dostępne stacje: {stations_list}

        Komenda: "{command}"

        Przykłady:
        - "pociąg z wałbrzycha szczawienka do wrocławia głównego" -> "WAŁBRZYCH SZCZAWIEŃKO,WROCŁAW GŁÓWNY"
        - "rozklad jazdy z jeleniej góry do legnicy" -> "JELENIA GÓRA,LEGNICA"
        - "kiedy odjeżdża pociąg z wrocławia" -> "WROCŁAW GŁÓWNY,"
        - "najbliższy pociąg do warszawy" -> ",WARSZAWA CENTRALNA"
        - "połączenie z krakowa do katowic" -> "KRAKÓW GŁÓWNY,KATOWICE"
        - "jak dojechać z wwa do wrocławia" -> "WARSZAWA CENTRALNA,WROCŁAW GŁÓWNY"
        - "sprawdź kursy pociągów" -> ""
        - "pociąg do gdańska z poznańa" -> "POZNAŃ GŁÓWNY,GDAŃSK GŁÓWNY"
        - "z wrocławia głównego" -> "WROCŁAW GŁÓWNY,"
        - "do szczecina" -> ",SZCZECIN GŁÓWNY"

        Wynik:"""
        
        result = self.ask_ai(prompt, system_message).strip()
        
        if result:
            parts = result.split(',')
            if len(parts) == 2:
                start_station = parts[0].strip().upper()
                end_station = parts[1].strip().upper()
                
                # Sprawdź czy stacje są na liście dostępnych
                # print("stacje: ", start_station, end_station)
                return start_station, end_station
        
        return "", ""

    def load_station_names(self, env_path=".env") -> list:
        """
        Wczytuje listę dostępnych stacji kolejowych z danych GTFS.
        
        Args:
            env_path (str): ścieżka do pliku .env (może zawierać ścieżkę do danych GTFS)
        
        Returns:
            list: Lista nazw stacji w formacie WIELKIMI LITERAMI
        """
        try:
            # Wczytaj dane GTFS - możesz dostosować ścieżkę do swoich potrzeb
            stops_df = pd.read_csv("trains/stops.txt")
            
            # Pobierz unikalne nazwy stacji i posortuj je
            stations = stops_df['stop_name'].unique().tolist()
            
            # Konwertuj do wielkich liter i usuń duplikaty spowodowane różnicami w wielkości liter
            stations_upper = list(set([station.upper() for station in stations]))
            
            # Posortuj alfabetycznie dla spójności
            stations_upper.sort()
            
            return stations_upper
            
        except Exception as e:
            print(f"Błąd podczas wczytywania stacji: {e}")
            return []