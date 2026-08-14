"""Tests für ``core.ausleihe_ausgabe`` — reine Funktionen ohne Netzwerk/Subprocess.

``install``/``update``/``start_server`` klonen/syncen/spawnen und sind nicht
Teil der Unit-Tests (extern). Hier nur ``host_url`` (liest ``.env`` PORT) —
tkinter-frei, schnell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import ausleihe_ausgabe as aa
from core import envtool, paths


@pytest.fixture
def fake_aa_repo(tmp_path: Path, monkeypatch) -> Path:
    """Biegt ``ausleihe-ausgabe`` auf ein tmp-Repo mit ``.env`` um."""
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    repo = tmp_path / "ausleihe-ausgabe"
    (repo / ".git").mkdir(parents=True)
    return repo


def test_host_url_default_port_ohne_env(fake_aa_repo: Path) -> None:
    # Kein .env → Default-Port 3443.
    assert aa.host_url() == "https://localhost:3443/host"


def test_host_url_liest_port_aus_env(fake_aa_repo: Path) -> None:
    envtool.write_env(paths.env_file("ausleihe-ausgabe"), {"PORT": "8443"})
    assert aa.host_url() == "https://localhost:8443/host"


def test_host_url_ignoriert_kaputten_port(fake_aa_repo: Path) -> None:
    envtool.write_env(paths.env_file("ausleihe-ausgabe"), {"PORT": "keine-zahl"})
    assert aa.host_url() == "https://localhost:3443/host"


def test_host_url_ignoriert_leeren_port(fake_aa_repo: Path) -> None:
    envtool.write_env(paths.env_file("ausleihe-ausgabe"), {"PORT": ""})
    assert aa.host_url() == "https://localhost:3443/host"


def test_konstanten_konsistent() -> None:
    assert aa.SERVER_MODULE == "server.main"
    assert aa.DEFAULT_PORT == 3443
    assert aa.AUSLEIHE_REPOS == ("ausleihe-api", "ausleihe-ausgabe")
    assert aa.HOST_PATH == "/host"
    assert aa.SUMATRA_HINT  # non-empty Hinweis


# --- _venv_is_stale: erkennt einen venv, dessen Console-Script-Pfade ins
# Leere zeigen (Verzeichnis wurde nach venv-Erstellung umbenannt/verschoben). ---

def _write_console_script(bin_dir: Path, name: str, python_ref: str) -> None:
    """Schreibt ein uv-artiges Console-Script mit gebacktem Python-Pfad."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / name).write_text(
        f"#!/bin/sh\n'exec' '{python_ref}' '-c' '' \"$@\"\n", encoding="utf-8"
    )


def test_venv_is_stale_ohne_venv(tmp_path: Path) -> None:
    assert aa._venv_is_stale(tmp_path / ".venv") is False


def test_venv_is_stale_frisch_am_aktuellen_ort(tmp_path: Path) -> None:
    # Console-Script referenziert den venv-Python AM aktuellen Ort → existiert.
    venv = tmp_path / ".venv"
    py = venv / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text("")  # existiert → Referenz gültig
    _write_console_script(venv / "bin", "playwright", str(py))
    assert aa._venv_is_stale(venv) is False


def test_venv_is_stale_nach_rename(tmp_path: Path) -> None:
    # venv am neuen Ort, aber Console-Script referenziert noch den ALTEN Pfad
    # (der nicht mehr existiert) → stale.
    old_python = tmp_path / "IServ-Ausleihe-Ausgabe" / ".venv" / "bin" / "python3"
    venv = tmp_path / "ausleihe-ausgabe" / ".venv"
    _write_console_script(venv / "bin", "playwright", str(old_python))
    assert aa._venv_is_stale(venv) is True


def test_venv_is_stale_ohne_console_scripts(tmp_path: Path) -> None:
    # venv mit bin/, aber ohne Console-Scripts → nicht stale.
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python3").write_text("")  # nur der Interpreter, kein Script
    assert aa._venv_is_stale(venv) is False
