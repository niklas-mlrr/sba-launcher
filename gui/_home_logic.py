"""Tkinter-freie Pure-Logic-Helfer für den Start-Tab und den Assistenten.

Diese Funktionen lassen sich ohne Display testen (Headless-VPS). Die GUI-
Module (``tab_home``, ``setup_wizard``) importieren sie hier, statt sie inline
zu duplizieren — so bleibt die Logik testbar, ohne tkinter zu benötigen.
"""

from __future__ import annotations

from core import ausleihe_ausgabe as aa
from core import gitops
from core.status import ToolStatus


def state_for(st: ToolStatus) -> str:
    """Leitet den Karten-Zustand aus einem ToolStatus ab.

    Reihenfolge: running → ready → partial → missing (wie ``tab_home._state_for``).
    """
    if st.running:
        return "running"
    if st.ready:
        return "ready"
    if st.installed:
        return "partial"
    return "missing"


def next_step(key: str, state: str, st: ToolStatus) -> str:
    """Plain-language nächster Schritt pro Karte — abgeleitet aus Zustand + Detail.

    ``st.detail`` ist die nicht-technische Quelle („Zugangsdaten fehlen",
    „wird noch vorbereitet", …) und wird hier zu einem ganzen Satz geformt.
    """
    if state == "running":
        return "Im Tab auf „Beenden“ klicken, wenn der Einsatz vorbei ist."
    if state == "ready":
        return "Im Tab auf „Starten“ klicken."
    if state == "partial":
        detail = st.detail[0].upper() + st.detail[1:] if st.detail else "Noch nicht bereit"
        return f"{detail} — im Tab unter „Verwaltung“ ergänzen."
    return "Unten auf „Einrichten“ klicken (einmalig)."


def ausleihe_installed() -> bool:
    """``True`` gdw. beide ausleihe-Repos installiert sind (wie setup_wizard)."""
    return all(gitops.status(name).installed for name in aa.AUSLEIHE_REPOS)


def bestand_installed() -> bool:
    """``True`` gdw. ausleihe-api installiert ist (Bestand-Tab-Voraussetzung)."""
    return gitops.status("ausleihe-api").installed


def barcode_installed() -> bool:
    """``True`` gdw. barcode-simple installiert ist."""
    return gitops.status("barcode-simple").installed
