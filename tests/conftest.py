"""Gemeinsame Test-Infrastruktur: Umbrella-Layout-Fixture + Repo-Helper.

Mehrere Testmodule (``test_ausleihe``, ``test_barcode``, ``test_bestand_cli``,
``test_config_io``, ``test_envtool``, ``test_gitops``, ``test_gui_helpers``,
``test_status``) biegen ``paths.launcher_root`` auf ein tmp-"Umbrella"-Verzeichnis
um, unter dem die Geschwister-Repos als Verzeichnisse (``../<name>``) simuliert
werden — echte Isolation vom realen Dateisystem, kein Netzwerk/Git nötig.

Dieses Modul extrahiert das gemeinsame Muster, damit es nicht 8x dupliziert wird.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import paths


@pytest.fixture
def umbrella(tmp_path: Path, monkeypatch) -> Path:
    """Umbrella-Layout: ``tmp_path/sba-launcher`` → Geschwister via ``../<name>``.

    ``paths.launcher_root`` wird auf ``tmp_path/sba-launcher`` gebogen, sodass
    ``paths.sibling(name) == tmp_path/<name>`` — jeder Test bekommt sein eigenes
    isoliertes Umbrella-Verzeichnis (kein shared State in ``/tmp``).
    """
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    return tmp_path


def make_repo(umbrella: Path, name: str) -> Path:
    """Legt ein Fake-Repo ``umbrella/name`` mit ``.git``-Unterordner an.

    Simuliert ein geklontes Geschwister-Repo für ``gitops``/``status``-Checks,
    die nur auf Existenz von ``.git`` prüfen — kein echtes Git nötig.
    """
    repo = umbrella / name
    (repo / ".git").mkdir(parents=True)
    return repo


# Rückwärtskompatibler Alias — Name, unter dem der Helper in test_status.py /
# test_gui_helpers.py ursprünglich definiert war.
_mark_installed = make_repo
