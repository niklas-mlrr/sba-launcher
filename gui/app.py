"""Hauptfenster des SBA-Launchers (Tkinter, dünn).

Phase 0: vier Tabs als Gerüst, keine Logik. Jeder Tab ist ein Platzhalter mit
Kurzbeschreibung und Hinweis auf die späteren Phasen. Die eigentliche Logik
(klone/update/start/stop, Bestand-Editor) wird in Phase 1–4 in ``core/``
implementiert und hier nur angebunden.

Aufbau bewusst simpel: ``ttk.Notebook`` mit vier ``ttk.Frame``s + eine
Statusleiste unten. Fenster zentriert, feste Mindestgröße.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core import prereqs
from gui import tab_ausleihe, tab_barcode, tab_bestand

# Tab-Titel. Tab 1 (ausleihe), 2 (bestand) und 3 (barcode) sind voll angebunden
# (Phase 1 + 2 + 3); der Hilfe-Tab bleibt Platzhalter bis Phase 5.
# ``render`` baut den Frame-Inhalt.
TABS: list[tuple[str, str]] = [
    ("Ausleihe-Ausgabe", "ausleihe"),
    ("Bestand", "bestand"),
    ("Barcode-Scanner", "barcode"),
    (
        "Hilfe",
        "Deutsche Erklärtexte pro Aktion, Link zur Nachfolge-Anleitung,\n"
        "Hinweis auf den „dauerhaften Notnagel“ (USB-Handscanner) und die\n"
        "ALLOW_BOOKING-Regel (Produktionsschutz).\n"
        "(Phase 5)",
    ),
]

WINDOW_TITLE = "SBA-Launcher"
WINDOW_MIN_W = 760
WINDOW_MIN_H = 520


def build_status_line() -> str:
    """Eine kurze Werkzeug-Statuszeile (uv/git/node) für die Statusleiste."""
    status = prereqs.check_all()
    parts = [
        ("uv", status["uv"]),
        ("git", status["git"]),
        ("node", status["node"]),
    ]
    return "  |  ".join(f"{label}: {'ok' if s.available else '—'}" for label, s in parts)


def build_app(root: tk.Tk) -> ttk.Notebook:
    """Baut Notebook + Statusleiste in ``root`` ein; liefert das Notebook.

    Rein deskriptiv — keine Logik, keine Core-Aufrufe außer ``prereqs.check_all``
    für die Statuszeile. Später hängen sich die Tab-Module (``tab_*``) ein.
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
            _populate_placeholder(frame, _title, key)

    # Statusleiste (unten): Werkzeug-Erkennung, gerüst-artig.
    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=8, pady=4)
    ttk.Label(bar, text=build_status_line()).pack(side="left")
    ttk.Label(bar, text="Phase 3 — Tab Bestand", foreground="#888").pack(
        side="right"
    )

    return notebook


def _populate_placeholder(parent: ttk.Frame, title: str, description: str) -> None:
    """Platzhalter-Content pro Tab (zentriert, nur Text)."""
    wrapper = ttk.Frame(parent)
    wrapper.pack(expand=True, fill="both", padx=24, pady=24)
    ttk.Label(wrapper, text=title, font=("TkDefaultFont", 14, "bold")).pack(
        anchor="w", pady=(0, 8)
    )
    ttk.Label(wrapper, text=description, justify="left").pack(anchor="w")
    ttk.Label(
        wrapper,
        text="Noch nicht implementiert — Gerüst steht, Logik folgt in den nächsten Phasen.",
        foreground="#888",
        justify="left",
    ).pack(anchor="w", pady=(16, 0))


def main() -> None:
    """Entry point: baut das Fenster und startet den Tkinter-Mainloop."""
    root = tk.Tk()
    build_app(root)
    root.mainloop()
