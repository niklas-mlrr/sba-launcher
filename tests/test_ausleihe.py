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


def test_venv_is_stale_windows_pfad_nicht_existiert(tmp_path: Path) -> None:
    # Console-Script mit Windows-Pfad (…\.venv\Scripts\python.exe), der auf
    # POSIX nicht existiert → stale True (Regex erkennt Windows-Pfad-Muster).
    venv = tmp_path / ".venv"
    (venv / "bin").mkdir(parents=True)
    win_path = r"C:\old\project\.venv\Scripts\python.exe"
    (venv / "bin" / "playwright").write_text(
        f"#!/bin/sh\n'exec' '{win_path}' '-c' '' \"$@\"\n", encoding="utf-8"
    )
    assert aa._venv_is_stale(venv) is True


# --- start_server Vorbedingungen -------------------------------------------


class _FakeManager:
    """SubprocessManager-Stub: zeichnet start auf, ohne echte Prozesse."""

    def __init__(self) -> None:
        self.started: list[tuple[list[str], Path | None, dict | None]] = []

    def start(
        self, cmd: list[str], cwd: Path | None = None, env: dict | None = None
    ) -> None:
        self.started.append((cmd, cwd, env))


def test_start_server_hebt_wenn_repo_fehlt(tmp_path: Path, monkeypatch) -> None:
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    with pytest.raises(FileNotFoundError, match="nicht installiert"):
        aa.start_server(_FakeManager())


def test_start_server_hebt_wenn_env_fehlt(fake_aa_repo: Path) -> None:
    # Repo da (fake_aa_repo legt .git an), aber keine .env.
    with pytest.raises(FileNotFoundError, match=r"\.env fehlt"):
        aa.start_server(_FakeManager())


def test_start_server_startet_kommando(fake_aa_repo: Path) -> None:
    envtool.write_env(
        paths.env_file("ausleihe-ausgabe"),
        {
            "ISERV_DOMAIN": "d",
            "ISERV_USERNAME": "u",
            "ISERV_PASSWORD": "p",
            "HOST_PASSWORD": "h",
        },
    )
    mgr = _FakeManager()
    aa.start_server(mgr)
    assert len(mgr.started) == 1
    cmd, cwd, _ = mgr.started[0]
    assert cmd == ["uv", "run", "python", "-m", aa.SERVER_MODULE]
    assert cwd.resolve() == fake_aa_repo.resolve()
