"""Start-Tab (Dashboard) — Startpunkt statt eines passiven Fußzeilen-Textes.

Zeigt für jedes der drei Werkzeuge eine Karte mit verständlichem Bereitschafts-
Status (:mod:`core.status`) und einem Knopf, der in den passenden Tab
springt. Der „Ersteinrichtung starten"-Knopf öffnet den geführten Assistenten
(:mod:`gui.setup_wizard`). Enthält selbst keine Orchestrierungslogik — reine
Anzeige + Navigation, wie alle ``gui/``-Module.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from core import status as status_mod
from gui import setup_wizard, theme

# Bereitschaftszustand → (Hintergrund, Text, Symbol) — dieselbe Palette wie
# gui.widgets.Banner, hier kompakt pro Karte statt als volle Bannerzeile.
_STATE_STYLES: dict[str, tuple[str, str, str]] = {
    "running": (theme.WARNING_BG, theme.WARNING_TEXT, "●"),
    "ready": (theme.SUCCESS_BG, theme.SUCCESS_TEXT, "✓"),
    "partial": (theme.INFO_BG, theme.INFO_TEXT, "i"),
    "missing": (theme.BG, theme.TEXT_MUTED, "○"),
}


def _state_for(st: status_mod.ToolStatus) -> str:
    if st.running:
        return "running"
    if st.ready:
        return "ready"
    if st.installed:
        return "partial"
    return "missing"


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
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(16, 4))
        ttk.Label(top, text="SBA-Launcher", style=theme.HEADING_LABEL).pack(anchor="w")
        ttk.Label(
            top,
            text="Startpunkt für die drei Werkzeuge der Schulbuchausleihe. Bei der "
            "ersten Nutzung auf diesem Laptop unten „Ersteinrichtung starten“ klicken.",
            style=theme.MUTED_LABEL,
            wraplength=780,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))
        ttk.Button(
            top,
            text="Ersteinrichtung starten",
            style=theme.PRIMARY_BUTTON,
            command=self._open_wizard,
        ).pack(anchor="w")

        cards_row = ttk.Frame(self)
        cards_row.pack(fill="both", expand=True, padx=16, pady=12)
        card_defs = (
            ("ausleihe", "Ausleihe & Ausgabe"),
            ("bestand", "Bestandsliste"),
            ("barcode", "Barcode-Scanner"),
        )
        for i, (key, label) in enumerate(card_defs):
            cards_row.columnconfigure(i, weight=1, uniform="card")
            self._cards[key] = self._build_card(cards_row, label, key)
            pad_left = 0 if i == 0 else 8
            self._cards[key]["frame"].grid(row=0, column=i, sticky="nsew", padx=(pad_left, 0))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Label(
            bottom,
            text="Bei einem Problem: Tab „Hilfe“ öffnen oder auf den USB-Handscanner "
            "und das offizielle IServ-Ausleihe-Frontend zurückfallen.",
            style=theme.MUTED_LABEL,
            wraplength=780,
            justify="left",
        ).pack(anchor="w")

    def _build_card(self, parent: tk.Widget, title: str, key: str) -> dict[str, tk.Widget]:
        frame = ttk.LabelFrame(parent, text=title, style=theme.CARD_FRAME)
        state_row = tk.Frame(frame, background=theme.SURFACE)
        state_row.pack(fill="x", padx=10, pady=(10, 4))
        symbol = tk.Label(
            state_row, text="", font=("TkDefaultFont", 11, "bold"), background=theme.SURFACE
        )
        symbol.pack(side="left")
        detail = tk.Label(state_row, text="", background=theme.SURFACE, anchor="w")
        detail.pack(side="left", padx=(6, 0), fill="x", expand=True)
        button = ttk.Button(frame, text="Öffnen", command=lambda: self._navigate(key))
        button.pack(anchor="w", padx=10, pady=(4, 10))
        return {"frame": frame, "symbol": symbol, "detail": detail, "button": button}

    def _open_wizard(self) -> None:
        setup_wizard.open_wizard(self, on_finish=self.refresh)

    # --- Aktualisierung ------------------------------------------------------

    def refresh(self) -> None:
        """Fragt :mod:`core.status` neu ab und aktualisiert alle drei Karten.

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
            bg, fg, symbol = _STATE_STYLES[_state_for(st)]
            card["symbol"].configure(text=symbol, foreground=fg, background=theme.SURFACE)
            card["detail"].configure(text=st.detail, foreground=fg, background=theme.SURFACE)


def build(
    parent: tk.Widget,
    navigate: Callable[[str], None] | None = None,
    running_getters: dict[str, Callable[[], bool]] | None = None,
) -> HomeTab:
    """Erzeugt den Start-Tab und liefert ihn (für ``gui.app``)."""
    return HomeTab(parent, navigate=navigate, running_getters=running_getters)
