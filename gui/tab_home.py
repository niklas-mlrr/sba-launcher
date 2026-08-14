"""Start-Tab (Dashboard) — Startpunkt statt eines passiven Fußzeilen-Textes.

Phase 9 — erweiterter Launcher (nicht Cockpit): jede Werkzeug-Karte zeigt einen
klaren Bereitschafts-Zustand + einen klaren, plain-language nächsten Schritt
statt nur einer kleinen Pille. Navigation-only — keine Aktion läuft von hier
aus (§6 Simplicity: common path first; §16 Wayfinding: „Was gibt es hier?
Wie komme ich weiter?").

Pro Karte:
1. **Zustands-Pille** — getönter Streifen mit Symbol + Headline („Bereit",
   „Läuft", „Fast bereit", „Einrichtung nötig"). Gleiche Status-Palette wie die
   ``StatusBar`` der Tabs → Dashboard und Tabs lesen als ein System.
2. **Nächster Schritt** — eine Zeile in Alltagssprache, die sagt, was im Tab
   ansteht („Im Tab auf ‚Ausleihe starten‘ klicken").
3. **Knöpfe** — „Öffnen" (springt in den Tab) und, falls nicht bereit,
   „Einrichten" (öffnet den Assistenten). Beides Navigation, kein Lauf.

Oben: Display-Titel + Einordnung + „Ersteinrichtung starten" (PRIMARY, öffnet
den Assistenten) + eine Gesamt-Bereitschaftszeile (:func:`core.status.all_ready`
— „Alles eingerichtet" vs „Einrichtung ausstehend").

Keine Orchestrierungslogik — reine Anzeige + Navigation, wie alle ``gui/``-
Module. ``refresh`` fragt :mod:`core.status` neu ab (kein Dauer-Polling).
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from core import status as status_mod
from gui import setup_wizard, theme
from gui._home_logic import next_step as _next_step
from gui._home_logic import state_for as _state_for

# Zustand → (Pillen-Hintergrund, Text, Symbol) — gleiche Status-Palette wie
# gui.widgets._BANNER_STYLES / StatusBar, hier kompakt pro Karte.
_STATE_STYLES: dict[str, tuple[str, str, str]] = {
    "running": (theme.WARNING_BG, theme.WARNING_TEXT, "●"),
    "ready": (theme.SUCCESS_BG, theme.SUCCESS_TEXT, "✓"),
    "partial": (theme.INFO_BG, theme.INFO_TEXT, "i"),
    "missing": (theme.SURFACE_2, theme.TEXT_MUTED, "○"),
}

# Zustand → Headline (kurz, eine Zeile) — der Blickfang-Text der Pille.
_STATE_HEADLINES: dict[str, str] = {
    "running": "Läuft",
    "ready": "Bereit",
    "partial": "Fast bereit",
    "missing": "Einrichtung nötig",
}


class HomeTab(ttk.Frame):
    """Dashboard: drei Werkzeug-Karten + Ersteinrichtungs-Assistent."""

    def __init__(
        self,
        parent: tk.Widget,
        navigate: Callable[[str], None] | None = None,
        running_getters: dict[str, Callable[[], bool]] | None = None,
        **kw,
    ) -> None:
        super().__init__(parent, **kw)
        self._navigate = navigate or (lambda _key: None)
        self._running_getters = running_getters or {}
        self._cards: dict[str, dict[str, tk.Widget]] = {}
        self._build()
        self.refresh()

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        # Kopf: großer Display-Titel + Einordnung + Hauptaktion + Gesamt-Status.
        top = ttk.Frame(self)
        top.pack(fill="x", padx=theme.SP_XL, pady=(theme.SP_XL, theme.SP_SM))
        ttk.Label(top, text="SBA-Launcher", style=theme.DISPLAY_LABEL).pack(anchor="w")
        ttk.Label(
            top,
            text="Startpunkt für die drei Werkzeuge der Schulbuchausleihe. Bei der "
            "ersten Nutzung auf diesem Laptop unten „Ersteinrichtung starten“ klicken.",
            style=theme.MUTED_LABEL,
            wraplength=860,
            justify="left",
        ).pack(anchor="w", pady=(theme.SP_SM, theme.SP_MD))
        ttk.Button(
            top,
            text="Ersteinrichtung starten",
            style=theme.PRIMARY_BUTTON,
            command=self._open_wizard,
        ).pack(anchor="w")

        # Gesamt-Bereitschaftszeile — eine Aussage über alle drei Werkzeuge.
        self._readiness_row = ttk.Frame(top)
        self._readiness_row.pack(fill="x", pady=(theme.SP_SM, 0))
        self._readiness_glyph = tk.Label(
            self._readiness_row, text="", font=theme.BODY_BOLD, padx=0
        )
        self._readiness_glyph.pack(side="left", padx=(0, theme.SP_XS))
        self._readiness_label = tk.Label(
            self._readiness_row, text="", font=theme.BODY, anchor="w"
        )
        self._readiness_label.pack(side="left", fill="x", expand=True)

        # Drei Karten nebeneinander.
        cards_row = ttk.Frame(self)
        cards_row.pack(fill="both", expand=True, padx=theme.SP_XL, pady=theme.SP_MD)
        card_defs = (
            ("ausleihe", "Ausleihe & Ausgabe"),
            ("bestand", "Bestandsliste"),
            ("barcode", "Barcode-Scanner"),
        )
        for i, (key, label) in enumerate(card_defs):
            cards_row.columnconfigure(i, weight=1, uniform="card")
            self._cards[key] = self._build_card(cards_row, label, key)
            pad_left = 0 if i == 0 else theme.SP_MD
            self._cards[key]["frame"].grid(
                row=0, column=i, sticky="nsew", padx=(pad_left, 0)
            )

        # Fußnote: Notnagel-Hinweis.
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=theme.SP_XL, pady=(0, theme.SP_XL))
        ttk.Label(
            bottom,
            text="Bei einem Problem: Tab „Hilfe“ öffnen oder auf den USB-Handscanner "
            "und das offizielle IServ-Ausleihe-Frontend zurückfallen.",
            style=theme.MUTED_LABEL,
            wraplength=860,
            justify="left",
        ).pack(anchor="w")

    def _build_card(self, parent: tk.Widget, title: str, key: str) -> dict[str, tk.Widget]:
        frame = ttk.LabelFrame(parent, text=title, style=theme.CARD_FRAME)
        inner = ttk.Frame(frame, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=theme.SP_MD, pady=theme.SP_MD)

        # Zustands-Pille: getönter Hintergrund + Symbol + Headline.
        pill = tk.Frame(inner, background=theme.SURFACE_2)
        pill.pack(fill="x", pady=(0, theme.SP_SM))
        symbol = tk.Label(
            pill, text="", font=theme.HEADING, padx=theme.SP_SM, pady=theme.SP_SM
        )
        symbol.pack(side="left")
        headline = tk.Label(
            pill, text="", font=theme.SUBHEADING, anchor="w", pady=theme.SP_SM
        )
        headline.pack(side="left", fill="x", expand=True, padx=(0, theme.SP_SM))

        # Nächster Schritt — eine Zeile plain-language, was im Tab ansteht.
        next_step = ttk.Label(
            inner, text="", style=theme.CARD_MUTED_LABEL, wraplength=260,
            justify="left", anchor="w",
        )
        next_step.pack(fill="x", pady=(0, theme.SP_MD))

        # Knöpfe: „Öffnen" immer; „Einrichten" nur, wenn nicht bereit.
        actions = ttk.Frame(inner, style="Card.TFrame")
        actions.pack(fill="x")
        open_btn = ttk.Button(
            actions, text="Öffnen", style=theme.SECONDARY_BUTTON,
            command=lambda: self._navigate(key),
        )
        open_btn.pack(side="left", padx=(0, theme.SP_SM))
        setup_btn = ttk.Button(
            actions, text="Einrichten", style=theme.SECONDARY_BUTTON,
            command=self._open_wizard,
        )
        # setup_btn wird in refresh() je nach Bereitschaft gepackt/vergessen.
        return {
            "frame": frame,
            "pill": pill,
            "symbol": symbol,
            "headline": headline,
            "next_step": next_step,
            "open_btn": open_btn,
            "setup_btn": setup_btn,
        }

    def _open_wizard(self) -> None:
        setup_wizard.open_wizard(self, on_finish=self.refresh)

    # --- Aktualisierung ------------------------------------------------------

    def refresh(self) -> None:
        """Fragt :mod:`core.status` neu ab und aktualisiert alle Karten + Gesamtzeile.

        Öffentlich, damit ``gui/app.py`` beim Wechsel auf diesen Tab und der
        Assistent nach dem Schließen neu laden können — kein Dauer-Polling
        (Git-/Dateisystem-Abfragen sind nicht kostenlos).
        """
        overview = status_mod.overview(
            ausleihe_running=self._running_getters.get("ausleihe", lambda: False)(),
            barcode_running=self._running_getters.get("barcode", lambda: False)(),
        )
        for st in overview:
            card = self._cards.get(st.key)
            if card is None:
                continue
            state = _state_for(st)
            bg, fg, symbol = _STATE_STYLES[state]
            card["pill"].configure(background=bg)
            card["symbol"].configure(text=symbol, foreground=fg, background=bg)
            card["headline"].configure(
                text=_STATE_HEADLINES[state], foreground=fg, background=bg
            )
            card["next_step"].configure(text=_next_step(st.key, state, st))

            # „Öffnen" ist PRIMARY, wenn bereit/laufend (der Normalfall); sonst
            # SECONDARY. Genau eine Hauptaktion pro Karte (§6 Simplicity).
            open_style = (
                theme.PRIMARY_BUTTON if state in ("running", "ready") else theme.SECONDARY_BUTTON
            )
            card["open_btn"].configure(style=open_style)

            # „Einrichten" nur anzeigen, wenn das Werkzeug noch nicht bereit ist.
            if st.ready:
                card["setup_btn"].pack_forget()
            else:
                card["setup_btn"].pack(side="left")

        # Gesamt-Bereitschaftszeile: alle einsatzbereit vs Einrichtung ausstehend.
        if status_mod.all_ready(overview):
            self._readiness_glyph.configure(
                text="✓", foreground=theme.SUCCESS_TEXT, background=theme.BG
            )
            self._readiness_label.configure(
                text="Alles eingerichtet — alle drei Werkzeuge sind einsatzbereit.",
                foreground=theme.SUCCESS_TEXT, background=theme.BG,
            )
        else:
            self._readiness_glyph.configure(
                text="○", foreground=theme.TEXT_MUTED, background=theme.BG
            )
            self._readiness_label.configure(
                text="Einrichtung ausstehend — siehe Karten unten.",
                foreground=theme.TEXT_MUTED, background=theme.BG,
            )


def build(
    parent: tk.Widget,
    navigate: Callable[[str], None] | None = None,
    running_getters: dict[str, Callable[[], bool]] | None = None,
) -> HomeTab:
    """Erzeugt den Start-Tab und liefert ihn (für ``gui.app``)."""
    return HomeTab(parent, navigate=navigate, running_getters=running_getters)
