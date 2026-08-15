"""Smoke-Tests für die GUI-Tabs — konstruieren jeden Tab in einem hidden root.

Skipped auf dem headless VPS (kein tkinter). Läuft auf dem Windows-Laptop,
wo tkinter installiert ist — dort stellt es sicher, dass jeder Tab ohne
Exception erzeugt wird.

Isolation: die Tab-Konstruktion ruft ``core.status`` (``overview``/
``bestand_status``/``barcode_status``) auf, die wiederum echte
gitops-/node-Subprocess-Aufrufe machen — auf einer Maschine ohne git/node im
PATH (oder ohne die Geschwister-Repos geklont) macht das den Smoke-Test
flaky. Ein autouse-Fixture patcht diese Getter auf kanonische
``ToolStatus``-Objekte, sodass der Test rein GUI-Konstruktion prüft.
"""

from __future__ import annotations

import pytest

# Modul-Level-Skip: tkinter fehlt auf dem headless VPS → gesamte Datei skippt.
tkinter = pytest.importorskip("tkinter", reason="tkinter nicht installiert (headless)")

import tkinter as tk  # noqa: E402

from core import catalog  # noqa: E402
from core.status import ToolStatus  # noqa: E402
from gui import (  # noqa: E402
    tab_ausleihe,
    tab_barcode,
    tab_bestand,
    tab_help,
    tab_home,
)

_CANNED_STATUS = ToolStatus("x", "X", False, False, False, "Einrichtung nötig")


@pytest.fixture(scope="module")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture(autouse=True)
def _isolate_status(monkeypatch) -> None:
    """Ersetzt die ``core.status``-Getter durch kanonische ``ToolStatus``-Werte.

    Verhindert echte gitops-/node-Subprocess-Aufrufe während der reinen
    Tab-Konstruktion (s. Modul-Docstring).
    """
    monkeypatch.setattr(
        tab_home.status_mod,
        "overview",
        lambda **kw: [_CANNED_STATUS, _CANNED_STATUS, _CANNED_STATUS],
    )
    monkeypatch.setattr(tab_bestand.status_mod, "bestand_status", lambda: _CANNED_STATUS)
    monkeypatch.setattr(
        tab_barcode.status_mod, "barcode_status", lambda running=False: _CANNED_STATUS
    )


_TAB_MODULES = [tab_ausleihe, tab_barcode, tab_bestand, tab_help, tab_home]


@pytest.mark.parametrize("mod", _TAB_MODULES)
def test_tab_konstruktion_ohne_exception(root, mod) -> None:
    """Jeder Tab lässt sich in einem hidden root konstruieren (keine Exception)."""
    mod.build(root)


# --- Wave 2 HIGH fix: Katalog-Editor löst Einträge per Index, nicht per e.id -


def test_katalog_edit_remove_wirken_per_index_nicht_per_nicht_eindeutiger_id(
    root, monkeypatch
) -> None:
    """Zwei Einträge mit derselben (nicht eindeutigen) ``id`` — Edit/Remove auf
    Index 1 lässt Index 0 unangetastet (statt beide zu treffen).
    """
    tab = tab_bestand.build(root)

    e1 = catalog.Eintrag(fach="Deutsch", jahrgang_von=5, jahrgang_bis=5, isbn="9783062052224")
    e2 = catalog.Eintrag(fach="Deutsch", jahrgang_von=5, jahrgang_bis=5, isbn="9783062052224")
    assert e1.id == e2.id  # gleiche Identität → kollidierende id (per Design)
    tab._katalog.eintraege = [e1, e2]
    tab._populate_tree()

    # Bearbeiten von Index 1 ("row1") — Index 0 muss unverändert bleiben.
    updated = catalog.Eintrag(fach="Mathe", jahrgang_von=6, jahrgang_bis=6, isbn="999")
    tab._tree.selection_set("row1")
    monkeypatch.setattr(tab, "_edit_dialog", lambda eintrag=None: updated)
    tab.on_katalog_edit()
    assert tab._katalog.eintraege[0].fach == "Deutsch"
    assert tab._katalog.eintraege[0].isbn == "9783062052224"
    assert tab._katalog.eintraege[1].fach == "Mathe"

    # Entfernen von Index 0 — nur dieser Eintrag verschwindet.
    tab._tree.selection_set("row0")
    monkeypatch.setattr("gui.tab_bestand.confirm_action", lambda *a, **k: True)
    tab.on_katalog_remove()
    assert len(tab._katalog.eintraege) == 1
    assert tab._katalog.eintraege[0].fach == "Mathe"
