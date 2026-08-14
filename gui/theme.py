"""Visuelles Design-System des Launchers (Farben, Schrift, ttk-Styles).

Phase 6: ein zentraler Ort für Farben/Schriftgrößen/Button-Hierarchie statt
verstreuter Hex-Werte in jedem Tab. Reines ``ttk.Style`` — keine neuen
Abhängigkeiten. :func:`apply` wird einmal beim Fensteraufbau gerufen
(``gui/app.py``); alle Tabs greifen danach nur noch auf die Farb-/Style-
Konstanten hier zu.

tkinter-frei ist dieses Modul NICHT (importiert ``tkinter``/``ttk`` direkt) —
wie der Rest von ``gui/`` nur auf dem Windows-/macOS-Laptop lauffähig, aber
``py_compile``-geprüft auf dem headless VPS.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from tkinter import ttk

# --- Farbpalette ------------------------------------------------------------
# Ein Akzent (primäre, sichere Aktion), ein Warnton (Aktion ändert Daten),
# ein gedeckter Ton (seltene/technische Aktion). Zusätzlich Status-Farben für
# Banner und Log-Zeilen (Erfolg/Fehler/Info/Warnung).

BG = "#f4f6f8"
SURFACE = "#ffffff"
BORDER = "#d8dee4"
TEXT = "#1f2937"
TEXT_MUTED = "#5b6572"

ACCENT = "#2563eb"          # primäre, sichere Aktion (Start/Prüfen)
ACCENT_HOVER = "#1d4ed8"
NEUTRAL = "#eef1f4"         # sekundäre Aktion (Einrichtung/Aktualisieren)
NEUTRAL_TEXT = "#334155"
DANGER = "#dc2626"          # Aktion überschreibt/ändert Daten
DANGER_HOVER = "#b91c1c"

SUCCESS_BG = "#e7f6ec"
SUCCESS_TEXT = "#1a7f37"
ERROR_BG = "#fdecec"
ERROR_TEXT = "#b3261e"
WARNING_BG = "#fff6e5"
WARNING_TEXT = "#8a5a00"
INFO_BG = "#eaf1fb"
INFO_TEXT = "#1f4e8c"

LOG_BG = "#1e1e1e"
LOG_FG = "#d4d4d4"
LOG_SUCCESS = "#7ee787"
LOG_ERROR = "#ff7b72"
LOG_WARNING = "#f2cc60"

FONT_FAMILY = "TkDefaultFont"
FONT_SIZE_BASE = 11
FONT_SIZE_HEADING = 15
FONT_SIZE_SUBHEADING = 12

# Style-Namen (öffentliche API — Tabs referenzieren diese Strings).
PRIMARY_BUTTON = "Primary.TButton"
SECONDARY_BUTTON = "Secondary.TButton"
DANGER_BUTTON = "Danger.TButton"
CARD_FRAME = "Card.TLabelframe"
CARD_FRAME_LABEL = "Card.TLabelframe.Label"
HEADING_LABEL = "Heading.TLabel"
SUBHEADING_LABEL = "Subheading.TLabel"
MUTED_LABEL = "Muted.TLabel"


def apply(root: tk.Tk) -> ttk.Style:
    """Konfiguriert Fenster-Hintergrund + ttk-Styles; liefert das Style-Objekt.

    Einmal beim Fensteraufbau rufen (``gui/app.py``). Nutzt ``clam`` als
    Basis-Theme, falls verfügbar — das Default-Theme erlaubt auf manchen
    Plattformen keine Button-Hintergrundfarben (native Widgets).
    """
    style = ttk.Style(root)
    with contextlib.suppress(tk.TclError):
        # Plattform ohne "clam" — Standard-Theme bleibt, Farben best-effort.
        style.theme_use("clam")

    root.configure(background=BG)

    base_font = (FONT_FAMILY, FONT_SIZE_BASE)
    style.configure(".", font=base_font, background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=base_font)
    style.configure(
        HEADING_LABEL, font=(FONT_FAMILY, FONT_SIZE_HEADING, "bold"), background=BG
    )
    style.configure(
        SUBHEADING_LABEL, font=(FONT_FAMILY, FONT_SIZE_SUBHEADING, "bold"), background=BG
    )
    style.configure(MUTED_LABEL, foreground=TEXT_MUTED, background=BG, font=base_font)

    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        font=(FONT_FAMILY, FONT_SIZE_BASE),
        padding=(14, 8),
    )

    style.configure(
        CARD_FRAME,
        background=SURFACE,
        bordercolor=BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        CARD_FRAME_LABEL, background=SURFACE, font=(FONT_FAMILY, FONT_SIZE_BASE, "bold")
    )

    # Button-Hierarchie: Primary (sicher/Hauptaktion) > Secondary (Einrichtung/
    # Aktualisierung) > Danger (überschreibt Daten — bewusst selten benutzt).
    style.configure(
        PRIMARY_BUTTON,
        font=(FONT_FAMILY, FONT_SIZE_BASE, "bold"),
        padding=(12, 8),
        background=ACCENT,
        foreground="#ffffff",
        bordercolor=ACCENT,
        focusthickness=0,
    )
    style.map(
        PRIMARY_BUTTON,
        background=[("active", ACCENT_HOVER), ("disabled", "#93b4f0")],
        foreground=[("disabled", "#f0f4fd")],
    )

    style.configure(
        SECONDARY_BUTTON,
        font=(FONT_FAMILY, FONT_SIZE_BASE),
        padding=(12, 8),
        background=NEUTRAL,
        foreground=NEUTRAL_TEXT,
        bordercolor=BORDER,
        focusthickness=0,
    )
    style.map(
        SECONDARY_BUTTON,
        background=[("active", "#e2e6ea"), ("disabled", "#f4f5f6")],
        foreground=[("disabled", "#a3aab2")],
    )

    style.configure(
        DANGER_BUTTON,
        font=(FONT_FAMILY, FONT_SIZE_BASE, "bold"),
        padding=(12, 8),
        background=DANGER,
        foreground="#ffffff",
        bordercolor=DANGER,
        focusthickness=0,
    )
    style.map(
        DANGER_BUTTON,
        background=[("active", DANGER_HOVER), ("disabled", "#eba7a2")],
        foreground=[("disabled", "#fdf0ef")],
    )

    style.configure("TEntry", padding=6, fieldbackground=SURFACE)
    style.configure("TSeparator", background=BORDER)

    return style
