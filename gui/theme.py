"""Visuelles Design-System des Launchers (Farben, Schrift, ttk-Styles).

Phase 7 — zweiter Design-Überarbeits-Pass nach Apple-Design-Prinzipien,
übersetzt für Tkinter (keine Springs/Vibrancy/Transparenz — Tk kann das
nicht; stattdessen: echte Schrift-Hierarchie, Surface-Kontrast als Tiefe,
Press-Feedback, ruhige Palette).

Zentrale Schriftstelle: ``apply()`` konfiguriert die eingebauten Tk-Named-
Fonts (``TkDefaultFont`` …) per :func:`tkinter.font.nametofont` sowie eigene
``App.*``-Named-Fonts und richtet die ttk-Styles darauf aus. Wird einmal beim
Fensteraufbau gerufen (``gui/app.py``), **bevor** Widgets erzeugt werden —
damit propagiert die Größe überall (auch Treeview/Notebook/Combobox, die
nicht erben und hier explizit gesetzt werden).

Hinweis zu Named-Fonts: Tuple wie ``("TkDefaultFont", 11, "bold")`` werden
von Tk als *Beschreibung* (family, size, weight) gelesen — ``"TkDefaultFont"``
ist darin ein nicht existierender Family-Name und fällt still auf den
System-Default mit fest Größe 11 zurück. Die Styles hier referenzieren
Named-Font-**Strings** (z. B. ``"App.Body"``), damit die Größe zentral
steuerbar ist und wirklich propagiert.

Wie der Rest von ``gui/`` importiert dieses Modul ``tkinter`` → nur auf dem
Windows-/macOS-Laptop lauffähig, aber ``py_compile``-geprüft auf dem
headless VPS.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# --- Farbpalette ------------------------------------------------------------
# Ruhige, Apple-angelehnte Light-Palette. Ein Akzent (primäre/sichere Aktion),
# ein Warnton (datenverändernd), ein gedeckter Ton (seltene/technische Aktion).
# Status-Farben für Banner und Log-Zeilen.

BG = "#f2f2f7"          # Fenster-/Seiten-Hintergrund (off-white)
SURFACE = "#ffffff"     # Karten-Oberfläche
SURFACE_2 = "#f9f9fb"   # sekundäre/sekundäre Zone, „Erweitert"-Karton
BORDER = "#e2e5ea"      # weicher Haar-Linien-Rahmen
HALO = "#e9edf2"        # dezenter 2px-Halo um Karten (Surface-Kontrast, kein Schatten)

TEXT = "#1c1c1e"
TEXT_MUTED = "#8a8a8e"

ACCENT = "#007aff"          # systemBlue — primäre, sichere Aktion
ACCENT_HOVER = "#0066d6"
ACCENT_PRESSED = "#1a3fa8"
ACCENT_DISABLED = "#9bc2ff"

NEUTRAL = "#eef1f4"         # sekundäre Aktion (Einrichtung/Aktualisieren)
NEUTRAL_TEXT = "#334155"
NEUTRAL_ACTIVE = "#e2e6ea"
NEUTRAL_PRESSED = "#d6dbe1"
NEUTRAL_DISABLED = "#f4f5f6"
NEUTRAL_TEXT_DISABLED = "#a3aab2"

DANGER = "#ff3b30"          # systemRed — Aktion überschreibt/ändert Daten
DANGER_HOVER = "#e02e24"
DANGER_PRESSED = "#cc261d"
DANGER_DISABLED = "#f3a39e"

SUCCESS_BG = "#e7f6ec"
SUCCESS_TEXT = "#1a7f37"
ERROR_BG = "#fdecec"
ERROR_TEXT = "#b3261e"
WARNING_BG = "#fff6e5"
WARNING_TEXT = "#8a5a00"
INFO_BG = "#e8f0fb"
INFO_TEXT = "#1f4e8c"

# Log-Panel: bewusst hell (integriert in die Chrome statt schwarzes Loch).
# Tag-Farben auf dunkel-auf-hell getunt (die alten dark-bg-Farben sähen auf
# hell kaputt aus) — sie nutzen die Status-Text-Palette.
LOG_BG = "#f7f7fa"
LOG_FG = "#1c1c1e"
LOG_SUCCESS = SUCCESS_TEXT
LOG_ERROR = ERROR_TEXT
LOG_WARNING = WARNING_TEXT

# --- Schriftgrößen ----------------------------------------------------------
SIZE_BODY = 14
SIZE_CAPTION = 13
SIZE_SUBHEADING = 16
SIZE_HEADING = 22
SIZE_DISPLAY = 28
SIZE_MONO = 13

# --- Named-Font-Namen (öffentliche API — Widgets referenzieren diese Strings) -
# Eingebaute Tk-Fonts werden in ``apply`` per ``nametofont`` konfiguriert;
# ``App.*`` sind die eigene Hierarchie.
BODY = "App.Body"
BODY_BOLD = "App.BodyBold"
CAPTION = "App.Caption"
SUBHEADING = "App.Subheading"
HEADING = "App.Heading"
DISPLAY = "App.Display"
MONO = "TkFixedFont"

# --- Abstand-Tokens (statt verstreuter padx/pady-Magic-Numbers) -------------
SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_LG = 16
SP_XL = 24
SP_XL2 = 32

# Reduzierte Bewegung (Tk kann ``prefers-reduced-motion`` nicht abfragen —
# env-gesteuert, für künftige dezente Effekte). Heute ohne Effekt, da wir
# bewusst auf Fades/Tweens verzichten (Tk kann sie nicht sauber).
REDUCED_MOTION = os.environ.get("SBA_REDUCED_MOTION", "").strip() not in ("", "0", "false")

# --- Style-Namen (öffentliche API — Tabs referenzieren diese Strings) --------
PRIMARY_BUTTON = "Primary.TButton"
SECONDARY_BUTTON = "Secondary.TButton"
DANGER_BUTTON = "Danger.TButton"
CARD_FRAME = "Card.TLabelframe"
CARD_FRAME_LABEL = "Card.TLabelframe.Label"
CARD_LABEL = "Card.TLabel"
CARD_SUBHEADING_LABEL = "Card.Subheading.TLabel"
CARD_MUTED_LABEL = "Card.Muted.TLabel"
DISPLAY_LABEL = "Display.TLabel"
HEADING_LABEL = "Heading.TLabel"
SUBHEADING_LABEL = "Subheading.TLabel"
MUTED_LABEL = "Muted.TLabel"
EYEBROW_LABEL = "Eyebrow.TLabel"  # kurzer, ehrlicher Zonen-Name (VERWALTUNG/PROTOKOLL)


def _platform_family() -> str | None:
    """Family-Override pro Plattform.

    Auf macOS/Linux ``None`` → TkDefaultFont behält seine plattformnative
    Family (``-apple-system``/``.AppleSystemUIFont`` sind *keine* Tk-Family-
    Namen und fielen still zurück). Auf Windows ist ``Segoe UI`` der eine
    sichere, etwas edlere Override.
    """
    if sys.platform == "win32":
        return "Segoe UI"
    return None


def _configure_fonts(root: tk.Tk) -> None:
    fam = _platform_family()

    def set_builtin(name: str, size: int, weight: str = "normal") -> None:
        f = tkfont.nametofont(name)
        if fam:
            f.configure(family=fam)
        f.configure(size=size, weight=weight)

    def app_font(name: str, size: int, weight: str = "normal") -> None:
        kw: dict[str, object] = {"size": size, "weight": weight}
        if fam:
            kw["family"] = fam
        try:
            tkfont.Font(root=root, name=name, **kw)  # type: ignore[arg-type]
        except tk.TclError:
            # Font existiert schon (z. B. erneuter Aufruf) → neu konfigurieren.
            tkfont.nametofont(name).configure(**kw)

    # Eingebaute Named-Fonts: propagieren in alle Widgets, die den String
    # referenzieren oder auf dem Tk-Default stehen.
    set_builtin("TkDefaultFont", SIZE_BODY)
    set_builtin("TkTextFont", SIZE_BODY)
    set_builtin("TkHeadingFont", SIZE_HEADING, "bold")
    set_builtin("TkMenuFont", SIZE_BODY)
    set_builtin("TkSmallCaptionFont", SIZE_CAPTION)
    set_builtin("TkFixedFont", SIZE_MONO)  # Family bleibt System-Mono.

    # Eigene Hierarchie.
    app_font(BODY, SIZE_BODY)
    app_font(BODY_BOLD, SIZE_BODY, "bold")
    app_font(CAPTION, SIZE_CAPTION)
    app_font(SUBHEADING, SIZE_SUBHEADING, "bold")
    app_font(HEADING, SIZE_HEADING, "bold")
    app_font(DISPLAY, SIZE_DISPLAY, "bold")


def _button(
    style: ttk.Style,
    name: str,
    bg: str,
    fg: str,
    active: str,
    pressed: str,
    disabled_bg: str,
    disabled_fg: str,
    *,
    bold: bool,
) -> None:
    style.configure(
        name,
        font=BODY_BOLD if bold else BODY,
        padding=(16, 10),
        background=bg,
        foreground=fg,
        bordercolor=bg,
        focusthickness=0,
        relief="flat",
    )
    # Reihenfolge: pressed vor active (ttk wertet die Map links-nach-rechts aus).
    style.map(
        name,
        background=[("pressed", pressed), ("active", active), ("disabled", disabled_bg)],
        foreground=[("disabled", disabled_fg)],
    )


def _configure_styles(style: ttk.Style, root: tk.Tk) -> None:
    # Wurzel-Style: alles erbt BODY, BG, TEXT.
    style.configure(".", font=BODY, background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=BODY)
    style.configure("TButton", font=BODY, padding=(16, 10), focusthickness=0)

    style.configure(DISPLAY_LABEL, font=DISPLAY, background=BG, foreground=TEXT)
    style.configure(HEADING_LABEL, font=HEADING, background=BG, foreground=TEXT)
    style.configure(SUBHEADING_LABEL, font=SUBHEADING, background=BG, foreground=TEXT)
    style.configure(MUTED_LABEL, font=CAPTION, foreground=TEXT_MUTED, background=BG)
    # Eyebrow: kurzer Zonen-Name. Tk kann kein Letter-Spacing — Großschreibung
    # + CAPTION + fett + gedeckt ist das web-„eyebrow"-Äquivalent (§15 Typo).
    style.configure(EYEBROW_LABEL, font=CAPTION, foreground=TEXT_MUTED, background=BG)

    # Notebook-Tabs: aktiver Tab = Surface, inaktive = Seite.
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, SP_SM, 0, 0))
    style.configure(
        "TNotebook.Tab",
        font=BODY,
        padding=(18, 10),
        background=BG,
        foreground=TEXT_MUTED,
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", SURFACE), ("active", SURFACE_2)],
        foreground=[("selected", TEXT), ("active", TEXT)],
    )

    # Karten: weiße Surface auf off-white Seite + weiche Haar-Linie. Der
    # Surface-vs-Seite-Kontrast IST die Tiefe (Tk kann keinen weichen Schatten).
    # ``CARD_FRAME`` = titelte Karte (LabelFrame, mit Rahmen); ``Card.TFrame``
    # = randloser Innen-Container derselben (siehe unten).
    style.configure(CARD_FRAME, background=SURFACE, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure(CARD_FRAME_LABEL, background=SURFACE, font=SUBHEADING, foreground=TEXT)

    # Karten-Innenraum: ``Card.TFrame`` (randlos, weiß) für Container innerhalb
    # einer Karte; Labels darin brauchen SURFACE als Hintergrund, sonst zeichnet
    # clam einen grauen BG-Fleck auf weiß (ein „billig"-Tells aus Phase 6).
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("Card.TLabel", background=SURFACE, foreground=TEXT, font=BODY)
    style.configure(
        "Card.Subheading.TLabel", background=SURFACE, foreground=TEXT, font=SUBHEADING
    )
    style.configure(
        "Card.Muted.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=CAPTION
    )

    # Button-Hierarchie: Primary (sicher/Hauptaktion) > Secondary (Einrichtung/
    # Aktualisierung) > Danger (überschreibt Daten). ``pressed`` gibt spürbares
    # Klick-Feedback (Tk kann keine Bewegung, aber Farbe beim Drücken).
    _button(
        style, PRIMARY_BUTTON, ACCENT, "#ffffff", ACCENT_HOVER, ACCENT_PRESSED,
        ACCENT_DISABLED, "#f0f4fd", bold=True,
    )
    _button(
        style, SECONDARY_BUTTON, NEUTRAL, NEUTRAL_TEXT, NEUTRAL_ACTIVE,
        NEUTRAL_PRESSED, NEUTRAL_DISABLED, NEUTRAL_TEXT_DISABLED, bold=False,
    )
    _button(
        style, DANGER_BUTTON, DANGER, "#ffffff", DANGER_HOVER, DANGER_PRESSED,
        DANGER_DISABLED, "#fdf0ef", bold=True,
    )

    # Eingaben: Treeview/Notebook/Combobox erben nicht automatisch → explizit.
    style.configure("TEntry", font=BODY, padding=8, fieldbackground=SURFACE,
                    bordercolor=BORDER)
    style.configure("TCombobox", font=BODY, fieldbackground=SURFACE)
    root.option_add("*TCombobox*Listbox.font", BODY)
    style.configure("TCheckbutton", font=BODY, background=BG, foreground=TEXT)
    style.configure(
        "Treeview", font=BODY, background=SURFACE, fieldbackground=SURFACE,
        foreground=TEXT, bordercolor=BORDER, rowheight=28,
    )
    style.configure(
        "Treeview.Heading", font=SUBHEADING, background=SURFACE_2,
        foreground=TEXT, bordercolor=BORDER, relief="solid", borderwidth=1,
    )
    style.configure("TSeparator", background=BORDER)
    style.configure("TProgressbar", background=ACCENT, troughcolor=SURFACE_2,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)


def apply(root: tk.Tk) -> ttk.Style:
    """Konfiguriert Named-Fonts + ttk-Styles; liefert das Style-Objekt.

    Einmal beim Fensteraufbau rufen (``gui/app.py``), **bevor** Widgets
    erzeugt werden. Nutzt ``clam`` als Basis-Theme (Default-Theme erlaubt auf
    manchen Plattformen keine Button-Hintergrundfarben).
    """
    style = ttk.Style(root)
    with contextlib.suppress(tk.TclError):
        style.theme_use("clam")

    root.configure(background=BG)
    _configure_fonts(root)
    _configure_styles(style, root)
    return style

