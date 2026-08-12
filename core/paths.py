r"""Pfad-Auflösung für die SBA-Geschwister-Repos.

Der Launcher liegt neben seinen Geschwistern (Ziel-Layout ``C:\SBA\``):

    C:\SBA\
    ├── sba-launcher\
    ├── ausleihe-ausgabe\
    ├── ausleihe-api\
    └── barcode-simple\

Jede Referenz läuft über ``sibling(name)`` → ``<launcher-root>/../<name>``.
Diese Konvention entspricht dem Bestand-Projekt (``../ausleihe-api``) und ist
der einzige Ort, an dem Geschwister-Pfade festgenagelt werden.
"""

from __future__ import annotations

import os
from pathlib import Path

# Reihenfolge ist Teil der API: Tab-Reihenfolge im GUI orientiert sich daran.
SIBLING_REPOS: tuple[str, ...] = (
    "ausleihe-ausgabe",
    "ausleihe-api",
    "barcode-simple",
)


def launcher_root() -> Path:
    """Root-Verzeichnis des sba-launcher-Repos (Heimat dieses Moduls).

    Aufgelöst relativ zum Dateisystem, NICHT zum CWD — so funktioniert der
    Aufruf egal, ob ``python launcher.py`` aus dem Repo-Root oder von anderswo
    gestartet wird.
    """
    # core/paths.py → Eltern = Repo-Root.
    return Path(__file__).resolve().parent.parent


def sibling(name: str) -> Path:
    """Pfad eines Geschwister-Repos, relativ zum Launcher-Root (``../<name>``).

    ``name`` wird nicht auf Existenz geprüft — ein fehlendes Repo ist ein
    legitimer Zustand (vor dem Klonen). Aufrufer prüft via :func:`exists`.
    """
    if name not in SIBLING_REPOS:
        raise ValueError(f"unbekanntes Geschwister-Repo: {name!r}")
    return launcher_root() / ".." / name


def exists(name: str) -> bool:
    """``True`` gdw. das Geschwister-Repo als Verzeichnis (mit .git) vorhanden ist."""
    path = sibling(name)
    return path.is_dir() and (path / ".git").exists()


def env_file(repo: str) -> Path:
    """``.env``-Pfad eines Geschwister-Repos (auch wenn das Repo fehlt)."""
    return sibling(repo) / ".env"


def tools_dir() -> Path:
    """Verzeichnis für per Bootstrap heruntergeladene Werkzeuge (git/node).

    Wird bedarfsweise angelegt; ``tools/`` ist gitignored.
    """
    return launcher_root() / "tools"


def data_dir() -> Path:
    """Verzeichnis für Launcher-eigene Daten (z. B. ``katalog.json``)."""
    path = launcher_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def templates_dir() -> Path:
    """Verzeichnis für Vorlagen (z. B. ``Bestand-Vorlage.xlsx``)."""
    return launcher_root() / "templates"


def as_posix_str(path: Path) -> str:
    """Posix-Stil-String (Forward-Slashes) — für CLI-Args über Subprocess."""
    return os.fspath(path).replace("\\", "/")
