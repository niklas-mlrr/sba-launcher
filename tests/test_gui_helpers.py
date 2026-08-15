"""Tests für ``gui._home_logic`` — Pure-Logic-Helfer ohne tkinter.

Läuft auf dem headless VPS (kein Display nötig). Testet die Zustands-Ableitung
(``state_for``/``next_step``) und die installiert-Checks, die aus
``tab_home``/``setup_wizard`` extrahiert wurden, um sie ohne tkinter testbar
zu machen.
"""

from __future__ import annotations

from pathlib import Path

from core.status import ToolStatus
from gui import _home_logic as hl
from tests.conftest import _mark_installed

# --- state_for --------------------------------------------------------------


def test_state_for_running() -> None:
    st = ToolStatus("x", "X", True, True, True, "läuft")
    assert hl.state_for(st) == "running"


def test_state_for_ready() -> None:
    st = ToolStatus("x", "X", True, True, False, "bereit")
    assert hl.state_for(st) == "ready"


def test_state_for_partial() -> None:
    st = ToolStatus("x", "X", True, False, False, "Zugangsdaten fehlen")
    assert hl.state_for(st) == "partial"


def test_state_for_missing() -> None:
    st = ToolStatus("x", "X", False, False, False, "Einrichtung nötig")
    assert hl.state_for(st) == "missing"


# --- next_step --------------------------------------------------------------


def test_next_step_running() -> None:
    st = ToolStatus("x", "X", True, True, True, "läuft")
    assert "Beenden" in hl.next_step("x", "running", st)


def test_next_step_ready() -> None:
    st = ToolStatus("x", "X", True, True, False, "bereit")
    assert "Starten" in hl.next_step("x", "ready", st)


def test_next_step_partial_nutzt_detail() -> None:
    st = ToolStatus("x", "X", True, False, False, "Zugangsdaten fehlen")
    step = hl.next_step("x", "partial", st)
    assert "Zugangsdaten fehlen" in step
    assert "Verwaltung" in step


def test_next_step_missing() -> None:
    st = ToolStatus("x", "X", False, False, False, "Einrichtung nötig")
    assert "Einrichten" in hl.next_step("x", "missing", st)


# --- installiert-Checks -----------------------------------------------------


def test_ausleihe_installed_false_wenn_nichts_da(umbrella: Path) -> None:
    assert hl.ausleihe_installed() is False


def test_ausleihe_installed_true_wenn_beide_da(umbrella: Path) -> None:
    _mark_installed(umbrella, "ausleihe-ausgabe")
    _mark_installed(umbrella, "ausleihe-api")
    assert hl.ausleihe_installed() is True


def test_ausleihe_installed_false_wenn_nur_eins_da(umbrella: Path) -> None:
    _mark_installed(umbrella, "ausleihe-api")
    assert hl.ausleihe_installed() is False


def test_bestand_installed(umbrella: Path) -> None:
    assert hl.bestand_installed() is False
    _mark_installed(umbrella, "ausleihe-api")
    assert hl.bestand_installed() is True


def test_barcode_installed(umbrella: Path) -> None:
    assert hl.barcode_installed() is False
    _mark_installed(umbrella, "barcode-simple")
    assert hl.barcode_installed() is True
