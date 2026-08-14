"""Hauptfenster des SBA-Launchers (Tkinter, dünn).

Das Fenster führt durch die drei Arbeitsabläufe und bietet eine Kurzhilfe für
Nachfolger ohne Programmierkenntnisse. Die eigentliche Orchestrierungslogik
bleibt in core/. Phase 6: der Start-Tab (Dashboard) ersetzt die frühere
passive Statuszeile — Bereitschaft ist jetzt sichtbar, nicht nur textuell.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gui import tab_ausleihe, tab_barcode, tab_bestand, tab_help, tab_home, theme

# Tab-Titel und interne Schlüssel; "Start" wird als erster Tab eingefügt,
# nachdem die drei Werkzeug-Tabs gebaut sind (siehe build_app).
TABS: list[tuple[str, str]] = [
    ("Ausleihe & Ausgabe", "ausleihe"),
    ("Bestandsliste", "bestand"),
    ("Barcode-Scanner", "barcode"),
    ("Hilfe", "help"),
]

WINDOW_TITLE = "SBA-Launcher – Schulbuchausleihe"
WINDOW_MIN_W = 980
WINDOW_MIN_H = 680


def build_app(root: tk.Tk) -> ttk.Notebook:
    """Baut Notebook + Start-Dashboard in ``root`` ein; liefert das Notebook.

    Die Tabs binden nur ihre Oberflächen an; die Arbeitslogik bleibt in core/.
    Reihenfolge im Notebook: Start (Dashboard) zuerst, dann die drei
    Werkzeug-Tabs, dann Hilfe — Start wird zuletzt eingefügt (Index 0), weil
    er Referenzen auf die bereits gebauten Werkzeug-Tabs braucht (Lauf-Status
    für die Dashboard-Karten).
    """
    root.title(WINDOW_TITLE)
    root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)
    theme.apply(root)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=theme.SP_SM, pady=theme.SP_SM)

    contents: dict[str, tk.Widget] = {}
    indices: dict[str, int] = {}
    for _title, key in TABS:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=_title)
        if key == "ausleihe":
            content = tab_ausleihe.build(frame)
        elif key == "bestand":
            content = tab_bestand.build(frame)
        elif key == "barcode":
            content = tab_barcode.build(frame)
        else:
            content = tab_help.build(frame)
        content.pack(fill="both", expand=True)
        contents[key] = content
        indices[key] = notebook.index("end") - 1

    def navigate(key: str) -> None:
        idx = indices.get(key)
        if idx is not None:
            notebook.select(idx)

    running_getters = {
        "ausleihe": contents["ausleihe"].is_running,
        "barcode": contents["barcode"].is_running,
    }
    home_frame = ttk.Frame(notebook)
    notebook.insert(0, home_frame, text="Start")
    home = tab_home.build(home_frame, navigate=navigate, running_getters=running_getters)
    home.pack(fill="both", expand=True)
    notebook.select(0)

    def on_tab_changed(_event: tk.Event) -> None:
        if notebook.index("current") == 0:
            home.refresh()

    notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

    return notebook


def main() -> None:
    """Entry point: baut das Fenster und startet den Tkinter-Mainloop."""
    root = tk.Tk()
    build_app(root)
    root.mainloop()
