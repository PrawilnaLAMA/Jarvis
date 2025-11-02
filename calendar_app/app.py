import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from core.calendar_manager import CalendarManager


class ModernCalendarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Kalendarz - Nowoczesny")
        self.root.configure(bg='#f0f0f0')
        self.cm = CalendarManager()
        
        # Konfiguracja stylów
        self.setup_styles()
        
        # Główny kontener
        main_frame = ttk.Frame(root, padding=15, style='Main.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Nagłówek
        header_frame = ttk.Frame(main_frame, style='Header.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(header_frame, text="Jarvis Kalendarz", 
                 font=('Segoe UI', 18, 'bold'), 
                 foreground='#2c3e50',
                 style='Header.TLabel').pack(pady=10)
        
        # Kontener z dwoma kolumnami
        content_frame = ttk.Frame(main_frame, style='Main.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Lewa kolumna - lista wydarzeń
        left_frame = ttk.Frame(content_frame, style='Card.TFrame')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        ttk.Label(left_frame, text="Zaplanowane Wydarzenia", 
                 style='CardHeader.TLabel').pack(pady=(10, 15))
        
        # Ramka dla listy z przewijaniem
        list_container = ttk.Frame(left_frame, style='Card.TFrame')
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Scrollbar dla listy
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Zwiększona czcionka w liście wydarzeń
        self.events_list = tk.Listbox(
            list_container, 
            yscrollcommand=scrollbar.set,
            bg='white',
            fg='#2c3e50',
            font=('Segoe UI', 12),
            selectbackground='#3498db',
            selectforeground='white',
            borderwidth=1,
            relief='solid',
            highlightthickness=0
        )
        self.events_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.events_list.yview)
        
        # Przyciski akcji
        button_frame = ttk.Frame(left_frame, style='Card.TFrame')
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(button_frame, text="Odśwież", 
                  command=self.refresh,
                  style='Accent.TButton').pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Usuń Zaznaczone", 
                  command=self.remove_selected,
                  style='Secondary.TButton').pack(side=tk.LEFT)
        
        # Prawa kolumna - formularz
        right_frame = ttk.Frame(content_frame, style='Card.TFrame')
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        ttk.Label(right_frame, text="Dodaj Nowe Wydarzenie", 
                 style='CardHeader.TLabel').pack(pady=(10, 20))
        
        # Formularz
        form_frame = ttk.Frame(right_frame, style='Card.TFrame')
        form_frame.pack(fill=tk.X, padx=15, pady=10)
        
        # Typ wydarzenia
        ttk.Label(form_frame, text="Typ Wydarzenia:", 
                 style='FormLabel.TLabel').grid(row=0, column=0, sticky=tk.W, pady=8)
        
        self.type_var = tk.StringVar(value="spotkanie")
        type_combo = ttk.Combobox(form_frame, textvariable=self.type_var,
                                 values=["spotkanie", "praca", "przypomnienie", "urodziny"],
                                 state="readonly", width=20)
        type_combo.grid(row=0, column=1, sticky=tk.W, pady=8, padx=(10, 0))
        
        # Data
        ttk.Label(form_frame, text="Data (RRRR-MM-DD):", 
                 style='FormLabel.TLabel').grid(row=1, column=0, sticky=tk.W, pady=8)
        
        self.date_var = tk.StringVar()
        date_entry = ttk.Entry(form_frame, textvariable=self.date_var, 
                 width=22, font=('Segoe UI', 10))
        date_entry.grid(row=1, column=1, sticky=tk.W, pady=8, padx=(10, 0))
        
        # Dni tygodnia (dla wydarzeń cyklicznych)
        ttk.Label(form_frame, text="Dni tygodnia:", 
                 style='FormLabel.TLabel').grid(row=2, column=0, sticky=tk.W, pady=8)
        
        self.days_var = tk.StringVar()
        days_entry = ttk.Entry(form_frame, textvariable=self.days_var,
                 width=22, font=('Segoe UI', 10))
        days_entry.grid(row=2, column=1, sticky=tk.W, pady=8, padx=(10, 0))
        
        ttk.Label(form_frame, text="np: poniedziałek,piątek", 
                 style='Hint.TLabel').grid(row=3, column=1, sticky=tk.W, pady=(0, 8))
        
        # Godzina rozpoczęcia
        ttk.Label(form_frame, text="Godzina rozpoczęcia:", 
                 style='FormLabel.TLabel').grid(row=4, column=0, sticky=tk.W, pady=8)
        
        self.start_var = tk.StringVar()
        start_entry = ttk.Entry(form_frame, textvariable=self.start_var,
                 width=22, font=('Segoe UI', 10))
        start_entry.grid(row=4, column=1, sticky=tk.W, pady=8, padx=(10, 0))
        
        ttk.Label(form_frame, text="GG:MM (24h)", 
                 style='Hint.TLabel').grid(row=5, column=1, sticky=tk.W, pady=(0, 8))
        
        # Opis
        ttk.Label(form_frame, text="Opis:", 
                 style='FormLabel.TLabel').grid(row=6, column=0, sticky=tk.W, pady=8)
        
        self.desc_var = tk.StringVar()
        desc_entry = ttk.Entry(form_frame, textvariable=self.desc_var, 
                              width=22, font=('Segoe UI', 10))
        desc_entry.grid(row=6, column=1, sticky=tk.W, pady=8, padx=(10, 0))
        
        # Przycisk dodawania
        ttk.Button(right_frame, text="Dodaj Wydarzenie", 
                  command=self.add_event,
                  style='Accent.TButton').pack(pady=20)
        
        # Status bar
        self.status_var = tk.StringVar(value="Gotowy")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var,
                              style='Status.TLabel')
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Lista do przechowywania ID wydarzeń dla łatwego dostępu
        self.event_ids = []
        
        self.refresh()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Główne style
        style.configure('Main.TFrame', background='#f8f9fa')
        style.configure('Header.TFrame', background='#3498db')
        style.configure('Header.TLabel', background='#3498db', foreground='white')
        
        # Karty
        style.configure('Card.TFrame', background='white', relief='raised', borderwidth=1)
        style.configure('CardHeader.TLabel', background='white', foreground='#2c3e50',
                       font=('Segoe UI', 12, 'bold'))
        
        # Przyciski
        style.configure('Accent.TButton', background='#3498db', foreground='white',
                       font=('Segoe UI', 10, 'bold'))
        style.map('Accent.TButton',
                 background=[('active', '#2980b9'), ('pressed', '#21618c')])
        
        style.configure('Secondary.TButton', background='#95a5a6', foreground='white',
                       font=('Segoe UI', 10))
        style.map('Secondary.TButton',
                 background=[('active', '#7f8c8d'), ('pressed', '#6c7a7d')])
        
        # Formularz
        style.configure('FormLabel.TLabel', background='white', foreground='#2c3e50',
                       font=('Segoe UI', 10, 'bold'))
        style.configure('Hint.TLabel', background='white', foreground='#7f8c8d',
                       font=('Segoe UI', 8))
        
        # Status bar
        style.configure('Status.TLabel', background='#34495e', foreground='white',
                       font=('Segoe UI', 9))

    def add_event(self):
        try:
            # Przygotowanie danych zgodnie z wymaganiami CalendarManager
            event_data = {
                "type": self.type_var.get().strip(),
                "date": self.date_var.get().strip() or None,
                "days": [d.strip() for d in self.days_var.get().split(',') if d.strip()],
                "start": self.start_var.get().strip() or None,
                "end": None,
                "desc": self.desc_var.get().strip()
            }
            
            # Sprawdzenie czy podano przynajmniej datę lub dni
            if not event_data["date"] and not event_data["days"]:
                messagebox.showerror("Błąd", "Podaj datę lub dni powtarzania")
                return
            
            # Dodanie wydarzenia przez CalendarManager
            event_id = self.cm.add_event(event_data)
            
            if event_id:
                # Czyszczenie formularza po udanym dodaniu
                self.date_var.set("")
                self.days_var.set("")
                self.start_var.set("")
                self.desc_var.set("")
                
                self.status_var.set("Wydarzenie dodane pomyślnie")
                self.refresh()
            else:
                messagebox.showerror("Błąd", "Nie udało się dodać wydarzenia")
                
        except Exception as e:
            messagebox.showerror("Błąd", f"Wystąpił błąd: {str(e)}")

    def refresh(self):
        self.cm.load_events()
        self.events_list.delete(0, tk.END)
        self.event_ids = []  # Reset listy ID
        
        for event in self.cm.list_events():
            event_id = event.get('id', '')
            event_type = event.get('type', '')
            event_date = event.get('date', '')
            event_days = event.get('days', [])
            event_start = event.get('start', '')
            event_desc = event.get('desc', '')
            
            # Tłumaczenie typów wydarzeń na polski
            type_translation = {
                "appointment": "spotkanie",
                "work": "praca", 
                "reminder": "przypomnienie",
                "birthday": "urodziny",
                "spotkanie": "spotkanie",
                "praca": "praca",
                "przypomnienie": "przypomnienie",
                "urodziny": "urodziny"
            }
            
            translated_type = type_translation.get(event_type, event_type)
            
            # Formatowanie wyświetlania - BEZ ID
            if event_date:
                # Wydarzenie jednorazowe z datą
                time_info = f"{event_start}" if event_start else ""
                label = f"{event_date} {time_info} - {event_desc} [{translated_type}]"
            else:
                # Wydarzenie cykliczne z dniami
                days_str = ",".join(event_days)
                time_info = f"{event_start}" if event_start else ""
                label = f"{days_str} {time_info} - {event_desc} [{translated_type}]"
            
            # Dodajemy do listy wydarzeń bez ID
            self.events_list.insert(tk.END, label)
            # Zapamiętujemy ID dla późniejszego użycia
            self.event_ids.append(event_id)

    def remove_selected(self):
        selection = self.events_list.curselection()
        if not selection:
            messagebox.showwarning("Ostrzeżenie", "Proszę wybrać wydarzenie do usunięcia")
            return
            
        try:
            index = selection[0]
            # Używamy zapamiętanych ID zamiast parsować z tekstu
            event_id = self.event_ids[index]
            
            if self.cm.remove_event(event_id):
                self.status_var.set("Wydarzenie usunięte pomyślnie")
                self.refresh()
            else:
                messagebox.showerror("Błąd", "Nie udało się usunąć wydarzenia")
                
        except Exception as e:
            messagebox.showerror("Błąd", f"Wystąpił błąd: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x600")
    app = ModernCalendarApp(root)
    root.mainloop()