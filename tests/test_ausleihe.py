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
