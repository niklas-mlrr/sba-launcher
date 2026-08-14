"""Smoke-Tests für die GUI-Tabs — konstruieren jeden Tab in einem hidden root.

Skipped auf dem headless VPS (kein tkinter). Läuft auf dem Windows-Laptop,
wo tkinter installiert ist — dort stellt es sicher, dass jeder Tab ohne
Exception erzeugt wird.
"""

from __future__ import annotations

import pytest

# Modul-Level-Skip: tkinter fehlt auf dem headless VPS → gesamte Datei skippt.
tkinter = pytest.importorskip("tkinter", reason="tkinter nicht installiert (headless)")

import tkinter as tk  # noqa: E402

from gui import (  # noqa: E402
    tab_ausleihe,
    tab_barcode,
    tab_bestand,
    tab_help,
    tab_home,
)


@pytest.fixture(scope="module")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


_TAB_MODULES = [tab_ausleihe, tab_barcode, tab_bestand, tab_help, tab_home]


@pytest.mark.parametrize("mod", _TAB_MODULES)
def test_tab_konstruktion_ohne_exception(root, mod) -> None:
    """Jeder Tab lässt sich in einem hidden root konstruieren (keine Exception)."""
    mod.build(root)
