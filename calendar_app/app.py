import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from core.calendar_manager import CalendarManager


class CalendarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Calendar")
        self.cm = CalendarManager()

        self.frame = ttk.Frame(root, padding=10)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Events list
        self.events_list = tk.Listbox(self.frame, height=12, width=80)
        self.events_list.grid(row=0, column=0, columnspan=4, pady=(0, 10))

        # Simple form
        ttk.Label(self.frame, text="Type").grid(row=1, column=0)
        self.type_var = tk.StringVar(value="appointment")
        ttk.Entry(self.frame, textvariable=self.type_var).grid(row=1, column=1)

        ttk.Label(self.frame, text="Date (YYYY-MM-DD)").grid(row=2, column=0)
        self.date_var = tk.StringVar()
        ttk.Entry(self.frame, textvariable=self.date_var).grid(row=2, column=1)

        ttk.Label(self.frame, text="Days (Mon,Tue)").grid(row=1, column=2)
        self.days_var = tk.StringVar()
        ttk.Entry(self.frame, textvariable=self.days_var).grid(row=1, column=3)

        ttk.Label(self.frame, text="Start (HH:MM)").grid(row=2, column=2)
        self.start_var = tk.StringVar()
        ttk.Entry(self.frame, textvariable=self.start_var).grid(row=2, column=3)

        ttk.Label(self.frame, text="Desc").grid(row=3, column=0)
        self.desc_var = tk.StringVar()
        ttk.Entry(self.frame, textvariable=self.desc_var, width=50).grid(row=3, column=1, columnspan=3, sticky=tk.W)

        ttk.Button(self.frame, text="Add", command=CalendarManager.add_event).grid(row=4, column=0, pady=10)
        ttk.Button(self.frame, text="Refresh", command=self.refresh).grid(row=4, column=1)
        ttk.Button(self.frame, text="Remove Selected", command=self.remove_selected).grid(row=4, column=2)

        self.refresh()

    def refresh(self):
        self.cm.load_events()
        self.events_list.delete(0, tk.END)
        for e in self.cm.list_events():
            if e.get("date"):
                label = f"{e.get('date')} {e.get('start','')} - {e.get('desc','')}"
            else:
                days = ",".join(e.get('days',[]))
                label = f"{days} {e.get('start','')} - {e.get('desc','')}"
            self.events_list.insert(tk.END, f"{e.get('id')} | {label}")


    def remove_selected(self):
        sel = self.events_list.curselection()
        if not sel:
            return
        item = self.events_list.get(sel[0])
        event_id = item.split("|")[0].strip()
        self.cm.remove_event(event_id)
        self.refresh()


if __name__ == "__main__":
    root = tk.Tk()
    app = CalendarApp(root)
    root.mainloop()
