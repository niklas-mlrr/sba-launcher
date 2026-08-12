"""Voraussetzungs-Prüfungen für den Launcher (uv, git, Node).

Phase 0: reine Erkennung (was ist da?), kein Download. Das eigentliche
Bootstrap (uv installieren, PortableGit/Node entpacken) folgt in Phase 1
für die Tabs, nicht hier. Diese Funktionen halten sich an das
``start - portable.bat``-Muster (kein Admin, keine Installer) — vorbereitet,
aber noch nicht aktiviert.

Phase 2 ergänzt das portable Node-Bootstrap (:func:`ensure_node`): ist weder
``node`` im PATH noch ein entpacktes portables Node vorhanden, wird das
festgenagelte LTS-Zip (Windows x64) nach ``tools/`` geladen und entpackt —
kein Admin, kein Installer, konsistent mit dem ``start - portable.bat``-Muster
des Barcode-Repos. Der Download ist Windows-only (POSIX braucht kein portables
Node und hat kein Display für den Launcher).

Alle Funktionen sind tkinter-frei und auf dem headless VPS testbar (der
Download selbst ist ausgelagert in :func:`_download_portable_node` und in
Tests gemockt).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core import paths

# Portables Node.js (LTS „Jod"), festgenagelt für deterministische Downloads.
# 2026-08-12 aktuell; bei einem LTS-Update nur diese Konstante + URL ändern.
# Das Zip entpackt nach ``node-<version>-win-x64/`` (enthält node.exe + npm).
NODE_VERSION = "v22.23.2"
NODE_DOWNLOAD_URL = (
    f"https://nodejs.org/dist/{NODE_VERSION}/"
    f"node-{NODE_VERSION}-win-x64.zip"
)


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
    """Prüft ``node`` im PATH **oder** als entpacktes portables Node unter ``tools/``.

    Nur für den Barcode-Tab relevant. ``ensure_node()`` richtet das portable
    Node bei, falls System-node fehlt; hier wird nur erkannt, was da ist.
    """
    found = _which("node")
    if found:
        return ToolStatus("node", True, found, "PATH")
    portable = portable_node_exe()
    if portable is not None:
        return ToolStatus("node", True, str(portable), "tools/" + portable.parent.name)
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


# --- Portables Node (Phase 2: Barcode-Tab) -------------------------------
#
# ``start - portable.bat`` aus dem Barcode-Repo zeigt das Muster: Node-Zip
# entpacken, ``node\node.exe`` direkt aufrufen — kein Admin, kein Installer.
# Hier verallgemeinert: das Zip landet in ``tools/`` und entpackt sein
# Top-Level-Verzeichnis (``node-<version>-win-x64/``); darauf zeigen alle
# Helfer. ``npm`` liegt im selben Verzeichnis (``npm.cmd`` auf Windows).


def portable_node_dir() -> Path:
    """Verzeichnis des entpackten portablen Node (``tools/node-<ver>-win-x64``).

    Existenz wird nicht geprüft — ein fehlendes Verzeichnis ist ein legitimer
    Zustand (vor :func:`ensure_node`). Der Name folgt dem Top-Level-Ordner im
    Node-Zip, damit :func:`_download_portable_node` nur ``extractall`` braucht.
    """
    return paths.tools_dir() / f"node-{NODE_VERSION}-win-x64"


def portable_node_exe() -> Path | None:
    """Pfad zur portablen ``node.exe``, falls vorhanden; sonst ``None``."""
    exe = portable_node_dir() / "node.exe"
    return exe if exe.is_file() else None


def node_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Umgebung mit dem portablen Node-Verzeichnis vorne im ``PATH``.

    Hat das System bereits ``node`` im PATH, wird ``PATH`` unangetastet
    gelassen (System-Node hat Vorrang — keine Überraschung durch ein altes
    portables Node). Der Aufrufer reicht diese Umgebung an Subprocess-Aufrufe
    (``node server.js``, ``npm install``), damit die portablen Werkzeuge ohne
    globales PATH-Patchen gefunden werden.
    """
    env = dict(base if base is not None else os.environ)
    if _which("node") is None:
        pdir = portable_node_dir()
        if (pdir / "node.exe").is_file():
            env["PATH"] = os.pathsep.join([str(pdir), env.get("PATH", "")])
    return env


def _resolve(binname: str, env: dict[str, str]) -> str:
    """Löst ``binname`` über ``shutil.which`` im gegebenen ``PATH`` auf.

    Liefert den absoluten Pfad (robuster als ein bloßer Name — Windows'
    ``.cmd``-Aufrufe via Subprocess brauchen den vollen Pfad) oder den
    Namens-String als Fallback (System-Node auf POSIX findet das selbst).
    """
    found = shutil.which(binname, path=env.get("PATH"))
    return found or binname


def node_bin() -> str:
    """Absoluter Pfad zu ``node`` (System oder portabel) oder ``"node"``."""
    return _resolve("node", node_env())


def npm_bin() -> str:
    """Absoluter Pfad zu ``npm`` (System oder portabel) oder ``"npm"``.

    Auf Windows liefert das die ``npm.cmd`` — zusammen mit ``shell=True``
    beim Subprocess-Aufruf robust ausführbar.
    """
    return _resolve("npm", node_env())


def ensure_node(log: Callable[[str], None] | None = None) -> str:
    """Stellt ``node``+``npm`` bereit: System-node ODER portables Node.

    Reihenfolge: System-``node`` im PATH → portables Node unter ``tools/`` →
    Download des festgenagelten LTS-Zips nach ``tools/`` und Entpacken. Liefert
    eine menschenlesbare Statusmeldung (z. B. fürs LogView).

    Der Download ist Windows-only (POSIX braucht kein portables Node und der
    Launcher läuft dort ohnehin nicht). Auf dem headless VPS wird diese
    Funktion nicht gegen Produktion gerufen — Tests mocken den Download.
    """
    if _which("node") is not None:
        return "Node.js im PATH gefunden"
    exe = portable_node_exe()
    if exe is not None:
        return f"portables Node gefunden: {exe}"
    _download_portable_node(log or (lambda _msg: None))
    exe = portable_node_exe()
    if exe is None:
        raise RuntimeError(
            "portables Node konnte nicht bereitgestellt werden "
            f"(erwartet unter {portable_node_dir()})"
        )
    return f"portables Node installiert: {exe}"


def _download_portable_node(log: Callable[[str], None]) -> None:
    """Lädt das Node-LTS-Zip herunter und entpackt es nach ``tools/``.

    Windows-Ziel: das Zip enthält ``node.exe`` + ``npm.cmd`` für win-x64.
    Auf POSIX hebt die Funktion ab (ein win-x64-Zip wäre hier nutzlos).
    """
    if os.name != "nt":
        raise RuntimeError(
            "portables Node steht nur unter Windows zur Verfügung "
            "(POSIX verwendet System-Node)."
        )
    import urllib.request
    import zipfile

    tools = paths.tools_dir()
    tools.mkdir(parents=True, exist_ok=True)
    zip_path = tools / f"node-{NODE_VERSION}-win-x64.zip"
    log(f"Lade portables Node herunter: {NODE_DOWNLOAD_URL}")
    urllib.request.urlretrieve(NODE_DOWNLOAD_URL, str(zip_path))
    log("Entpacke portables Node …")
    with zipfile.ZipFile(zip_path) as z:
        # ``extractall`` legt das Top-Level-Verzeichnis (portable_node_dir)
        # selbst an — kein manuelles Verschieben nötig.
        z.extractall(tools)
    zip_path.unlink(missing_ok=True)
