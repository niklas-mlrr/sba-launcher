"""Voraussetzungs-Prüfungen für den Launcher (uv, git, Node).

Phase 0: reine Erkennung (was ist da?), kein Download. Das eigentliche
Bootstrap (uv installieren, PortableGit/Node entpacken) folgt in Phase 1
für die Tabs, nicht hier. Diese Funktionen halten sich an das
``start - portable.bat``-Muster (kein Admin, keine Installer) — vorbereitet,
aber noch nicht aktiviert.

Alle Funktionen sind tkinter-frei und auf dem headless VPS testbar.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolStatus:
    """Erkennungs-Ergebnis für ein einzelnes Werkzeug.

    ``available`` über ``shutil.which`` (PATH) ODER bekannten absoluten Pfad.
    ``source`` ist menschenlesbar (z. B. ``"PATH"`` oder ``"tools/git/bin"``).
    """

    name: str
    available: bool
    path: str | None
    source: str

    def __str__(self) -> str:
        if not self.available:
            return f"{self.name}: FEHLT"
        return f"{self.name}: {self.path} ({self.source})"


def _which(name: str) -> str | None:
    return shutil.which(name)


def _version(cmd: list[str]) -> str | None:
    """Best-Effort Versionsstring (für Hinweistexte, nicht für Logik)."""
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.stderr or "").strip()
    # Erste Zeile reicht als Versionshinweis.
    return text.splitlines()[0] if text else None


def check_uv() -> ToolStatus:
    """Prüft ``uv`` im PATH. Wird von start.bat vorgebootet; hier nur Rückfrage."""
    found = _which("uv")
    if found:
        return ToolStatus("uv", True, found, "PATH")
    return ToolStatus("uv", False, None, "—")


def check_git() -> ToolStatus:
    """Prüft ``git`` im PATH (Standard auf dem Windows-Laptop der Ausleihe).

    Fallback-Pfad (Phase 1): PortableGit unter ``tools/git/bin`` voranstellen,
    falls System-git fehlt. Hier nur Erkennung des System-git.
    """
    found = _which("git")
    if found:
        return ToolStatus("git", True, found, "PATH")
    return ToolStatus("git", False, None, "—")


def check_node() -> ToolStatus:
    """Prüft ``node`` im PATH (nur für den Barcode-Tab relevant).

    Fallback-Pfad (Phase 1): portable Node-Zip nach ``tools/node/`` entpacken.
    """
    found = _which("node")
    if found:
        return ToolStatus("node", True, found, "PATH")
    return ToolStatus("node", False, None, "—")


def check_all() -> dict[str, ToolStatus]:
    """Alle drei Werkzeuge auf einmal (für den Help-/Status-Tab)."""
    return {
        "uv": check_uv(),
        "git": check_git(),
        "node": check_node(),
    }


def uv_version() -> str | None:
    return _version(["uv", "--version"])


def git_version() -> str | None:
    return _version(["git", "--version"])
