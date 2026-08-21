"""Tests für ``core.status`` — Bereitschafts-Übersicht der drei Werkzeuge.

tkinter-frei; nutzt dasselbe Umbrella-Muster wie ``test_gitops``/
``test_bestand_cli`` (Launcher-Root auf ``tmp_path`` gebogen, Repos als
lokale ``.git``-Verzeichnisse simuliert — kein echtes Git/Netzwerk nötig für
die reine Existenz-/Pfad-Logik, die dieses Modul zusammensetzt).
"""

from __future__ import annotations

from pathlib import Path

from core import barcode as bc
from core import bestand as bst
from core import paths, prereqs, status
from tests.conftest import _mark_installed

# --- ausleihe_status --------------------------------------------------------


def test_ausleihe_nicht_installiert(umbrella: Path) -> None:
    st = status.ausleihe_status()
    assert not st.installed
    assert not st.ready
    assert st.detail == "Einrichtung nötig"


def test_ausleihe_installiert_ohne_env(umbrella: Path) -> None:
    _mark_installed(umbrella, "ausleihe-ausgabe")
    _mark_installed(umbrella, "ausleihe-api")
    st = status.ausleihe_status()
    assert st.installed
    assert not st.ready
    assert st.detail == "Zugangsdaten fehlen"


def test_ausleihe_bereit_mit_env(umbrella: Path) -> None:
    _mark_installed(umbrella, "ausleihe-ausgabe")
    _mark_installed(umbrella, "ausleihe-api")
    paths.env_file("ausleihe-ausgabe").write_text(
        "ISERV_DOMAIN=trg\nISERV_USERNAME=u\nISERV_PASSWORD=p\nHOST_PASSWORD=h\n",
        encoding="utf-8",
    )
    st = status.ausleihe_status()
    assert st.ready
    assert st.detail == "bereit"


def test_ausleihe_laeuft(umbrella: Path) -> None:
    _mark_installed(umbrella, "ausleihe-ausgabe")
    _mark_installed(umbrella, "ausleihe-api")
    paths.env_file("ausleihe-ausgabe").write_text("ISERV_DOMAIN=trg\n", encoding="utf-8")
    st = status.ausleihe_status(running=True)
    assert st.running
    assert st.detail == "läuft"


# --- bestand_status ----------------------------------------------------------


def test_bestand_nicht_installiert(umbrella: Path) -> None:
    st = status.bestand_status()
    assert not st.installed
    assert not st.ready
    assert st.detail == "Einrichtung nötig"


def test_bestand_installiert_ohne_venv(umbrella: Path) -> None:
    _mark_installed(umbrella, "sba-bestand")
    _mark_installed(umbrella, "ausleihe-api")
    paths.env_file("ausleihe-api").write_text(
        "ISERV_DOMAIN=trg\nISERV_USERNAME=u\nISERV_PASSWORD=p\n", encoding="utf-8"
    )
    st = status.bestand_status()
    assert st.installed
    assert not st.ready
    assert st.detail == "wird noch vorbereitet"


def test_bestand_bereit(umbrella: Path) -> None:
    _mark_installed(umbrella, "sba-bestand")
    _mark_installed(umbrella, "ausleihe-api")
    paths.env_file("ausleihe-api").write_text(
        "ISERV_DOMAIN=trg\nISERV_USERNAME=u\nISERV_PASSWORD=p\n", encoding="utf-8"
    )
    venv_py = bst.bestand_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake", encoding="utf-8")
    st = status.bestand_status()
    assert st.ready
    assert st.detail == "bereit"


# --- barcode_status ------------------------------------------------------


def test_barcode_nicht_installiert(umbrella: Path) -> None:
    st = status.barcode_status()
    assert not st.installed
    assert st.detail == "Einrichtung nötig"


def test_barcode_bereit(umbrella: Path, monkeypatch) -> None:
    _mark_installed(umbrella, "barcode-scanner-simple")
    venv_py = bc.client_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(
        status.prereqs,
        "check_node",
        lambda: prereqs.ToolAvailability("node", True, "/usr/bin/node", "PATH"),
    )
    st = status.barcode_status()
    assert st.ready
    assert st.detail == "bereit"


# --- overview / all_ready --------------------------------------------------


def test_overview_reihenfolge(umbrella: Path) -> None:
    keys = [s.key for s in status.overview()]
    assert keys == ["ausleihe", "bestand", "barcode"]


def test_all_ready_false_wenn_nichts_installiert(umbrella: Path) -> None:
    assert not status.all_ready()
