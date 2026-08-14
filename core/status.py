"""Verständliche Bereitschafts-Übersicht der drei Werkzeuge (für die GUI).

Bündelt die verstreuten Status-Abfragen, die bisher in jedem Tab einzeln
zusammengebaut wurden (``gitops.status`` + venv-Existenz + Subprocess-Status),
zu einer einzigen, testbaren Quelle. Der laufende Subprocess-Status
(``running``) lebt nur in der GUI (SubprocessManager-Instanzen pro Tab) —
dieses Modul nimmt ihn daher als Parameter entgegen, statt ihn selbst zu
verwalten, und bleibt so tkinter-frei und auf dem headless VPS testbar.

Genutzt vom neuen Start-/Übersichts-Tab (Phase 6) und kann die bisherigen
``_refresh_status``-Duplikate in den Einzel-Tabs ersetzen.
"""

from __future__ import annotations

from dataclasses import dataclass

from core import ausleihe_ausgabe as aa
from core import barcode as bc
from core import bestand as bst
from core import envtool, gitops, prereqs


@dataclass(frozen=True)
class ToolStatus:
    """Bereitschaft eines einzelnen Werkzeugs, in Alltagssprache.

    ``installed`` = Repo(s) vorhanden. ``ready`` = zusätzlich einsatzbereit
    (Venv/Zugangsdaten da). ``running`` = ein Subprocess läuft gerade (nur
    Ausleihe + Barcode; Bestand ist ein Ein-Schuss-Lauf, immer ``False``).
    ``detail`` ist ein kurzer, nicht-technischer Statustext für die GUI.
    """

    key: str
    label: str
    installed: bool
    ready: bool
    running: bool
    detail: str


def ausleihe_status(running: bool = False) -> ToolStatus:
    """Bereitschaft von ausleihe-ausgabe (beide Repos + ``.env``)."""
    installed = all(gitops.status(name).installed for name in aa.AUSLEIHE_REPOS)
    env_ready = envtool.is_ready("ausleihe-ausgabe")
    ready = installed and env_ready
    if running:
        detail = "läuft"
    elif ready:
        detail = "bereit"
    elif installed:
        detail = "Zugangsdaten fehlen"
    else:
        detail = "Einrichtung nötig"
    return ToolStatus("ausleihe", "Ausleihe & Ausgabe", installed, ready, running, detail)


def bestand_status() -> ToolStatus:
    """Bereitschaft der Bestandsliste (Repo + ``.env`` + eigenes Venv)."""
    installed = gitops.status("ausleihe-api").installed
    env_ready = envtool.is_ready("ausleihe-api")
    venv_ready = bst.bestand_venv_python().is_file()
    ready = installed and env_ready and venv_ready
    if ready:
        detail = "bereit"
    elif not installed:
        detail = "Einrichtung nötig"
    elif not env_ready:
        detail = "Zugangsdaten fehlen"
    else:
        detail = "wird noch vorbereitet"
    return ToolStatus("bestand", "Bestandsliste", installed, ready, False, detail)


def barcode_status(running: bool = False) -> ToolStatus:
    """Bereitschaft des Barcode-Scanners (Repo + Client-Venv + Node)."""
    installed = gitops.status("barcode-simple").installed
    node_ok = prereqs.check_node().available
    ready = installed and node_ok and bc.client_venv_python().is_file()
    if running:
        detail = "läuft"
    elif ready:
        detail = "bereit"
    elif installed:
        detail = "wird noch vorbereitet"
    else:
        detail = "Einrichtung nötig"
    return ToolStatus("barcode", "Barcode-Scanner", installed, ready, running, detail)


def overview(
    ausleihe_running: bool = False, barcode_running: bool = False
) -> list[ToolStatus]:
    """Alle drei Werkzeuge in fester, GUI-passender Reihenfolge."""
    return [
        ausleihe_status(running=ausleihe_running),
        bestand_status(),
        barcode_status(running=barcode_running),
    ]


def all_ready(statuses: list[ToolStatus] | None = None) -> bool:
    """``True`` gdw. alle Werkzeuge einsatzbereit sind (für einen Gesamt-Haken)."""
    if statuses is None:
        statuses = overview()
    return all(s.ready for s in statuses)
