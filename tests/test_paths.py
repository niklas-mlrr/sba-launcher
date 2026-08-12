"""Tests für ``core.paths`` — Geschwister-Pfad-Auflösung.

Läuft tkinter-frei auf dem headless VPS. Verwendet ``tmp_path`` für IO; die
echten Geschwister-Repos werden nicht berührt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import paths


def test_launcher_root_liegt_im_repo_root():
    """``launcher_root()`` ist das Verzeichnis, das pyproject.toml enthält."""
    root = paths.launcher_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "launcher.py").is_file()
    # core/paths.py → Eltern.
    assert (root / "core" / "paths.py").is_file()


def test_sibling_ist_dotdot_name():
    """``sibling('ausleihe-ausgabe')`` → ``<root>/../ausleihe-ausgabe`` (raw, un-aufgelöst)."""
    expected = paths.launcher_root() / ".." / "ausleihe-ausgabe"
    assert paths.sibling("ausleihe-ausgabe") == expected


def test_sibling_ueberprueft_name():
    """Unbekannter Repo-Name wird abgewiesen (Tippfehlerschutz)."""
    with pytest.raises(ValueError, match="unbekanntes Geschwister-Repo"):
        paths.sibling("ausleihe-besterand")


@pytest.mark.parametrize("name", list(paths.SIBLING_REPOS))
def test_sibling_namen_abgedeckt(name: str):
    assert paths.sibling(name).name == name


def test_exists_verlangt_git_dir(tmp_path: Path, monkeypatch):
    """``exists`` verlangt ein ``.git``-Verzeichnis (kein zufälliger Ordner).

    Repo-Verzeichnis an genau dem Pfad, den ``sibling`` liefert (``../<name>``).
    """
    monkeypatch.setattr(paths, "launcher_root", lambda: tmp_path)
    repo = paths.sibling("ausleihe-ausgabe")
    repo.mkdir(parents=True, exist_ok=True)
    assert paths.exists("ausleihe-ausgabe") is False
    (repo / ".git").mkdir()
    assert paths.exists("ausleihe-ausgabe") is True


def test_env_file_ziel(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "launcher_root", lambda: tmp_path)
    assert paths.env_file("ausleihe-api") == (
        tmp_path / ".." / "ausleihe-api" / ".env"
    )


def test_tools_dir_unter_root():
    d = paths.tools_dir()
    assert d == paths.launcher_root() / "tools"


def test_data_dir_wird_erzeugt(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "launcher_root", lambda: tmp_path)
    d = paths.data_dir()
    assert d.is_dir()
    assert d == tmp_path / "data"


def test_templates_dir_unter_root():
    assert paths.templates_dir() == paths.launcher_root() / "templates"


def test_as_posix_str_konvertiert_backslashes(monkeypatch, tmp_path: Path):
    p = tmp_path / "sub" / "file.txt"
    assert "\\" not in paths.as_posix_str(p)
    assert "/" in paths.as_posix_str(p)
