"""Hauptfenster des SBA-Launchers (Tkinter, dünn).

Das Fenster führt durch die drei Arbeitsabläufe und bietet eine Kurzhilfe für
Nachfolger ohne Programmierkenntnisse. Die eigentliche Orchestrierungslogik
bleibt in core/.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core import prereqs
from gui import tab_ausleihe, tab_barcode, tab_bestand, tab_help

# Tab-Titel und interne Schlüssel für die vier Arbeitsbereiche.
TABS: list[tuple[str, str]] = [
    ("Ausleihe & Ausgabe", "ausleihe"),
    ("Bestandsliste", "bestand"),
    ("Barcode-Scanner", "barcode"),
    ("Hilfe", "help"),
]

WINDOW_TITLE = "SBA-Launcher – Schulbuchausleihe"
WINDOW_MIN_W = 760
WINDOW_MIN_H = 520


def build_status_line() -> str:
    """Eine kurze, nicht-technische Statuszeile für die Statusleiste."""
    status = prereqs.check_all()
    base_ready = status["uv"].available and status["git"].available
    barcode_ready = status["node"].available
    base_text = "bereit" if base_ready else "noch nicht vollständig"
    barcode_text = "bereit" if barcode_ready else "wird bei Bedarf eingerichtet"
    return f"Grundausstattung: {base_text}  |  Barcode-Scanner: {barcode_text}"


def build_app(root: tk.Tk) -> ttk.Notebook:
    """Baut Notebook + Statusleiste in ``root`` ein; liefert das Notebook.

    Die Tabs binden nur ihre Oberflächen an; die Arbeitslogik bleibt in core/.
    Die Statuszeile zeigt verständliche Zustände statt interner Programmnamen.
    """
    root.title(WINDOW_TITLE)
    root.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

    for _title, key in TABS:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=_title)
        if key == "ausleihe":
            # Phase 1: voll angebundener Tab (Logik in core.ausleihe_ausgabe).
            tab_ausleihe.build(frame)
        elif key == "bestand":
            # Phase 3: Bestand-Excel (Logik in core.bestand + core.config_io).
            tab_bestand.build(frame)
        elif key == "barcode":
            # Phase 2: Barcode-Scanner (Logik in core.barcode, zwei Subprozesse).
            tab_barcode.build(frame)
        else:
            tab_help.build(frame)

    # Statusleiste (unten): grobe, verständliche Bereitschaftshinweise.
    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=8, pady=4)
    ttk.Label(bar, text=build_status_line()).pack(side="left")
    ttk.Label(bar, text="Hilfe & einfache Bedienung", foreground="#888").pack(
        side="right"
    )

    return notebook


def main() -> None:
    """Entry point: baut das Fenster und startet den Tkinter-Mainloop."""
    root = tk.Tk()
    build_app(root)
    root.mainloop()
