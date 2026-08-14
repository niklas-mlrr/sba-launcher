"""Orchestrierung des ausleihe-ausgabe-Werkzeugs (install/update/start/stop).

Dieses Modul verbindet :mod:`gitops` (clone/pull), :mod:`envtool` (.env-Form)
und :mod:`process` (SubprocessManager) zu den vier Tab-Aktionen. Es hält die
Reihenfolge der Schritte ein (z. B. ausleihe-api vor ausleihe-ausgabe klonen,
da letzteres die API als editable Install aus ``../ausleihe-api`` bindet).

Produktionsschutz (CLAUDE.md):
- Der Launcher führt **keine** IServ-Schreibzugriffe aus. ``install``/``update``
  sind Git+uv, kein IServ-Kontakt.
- Der Server liest seine Credentials selbst aus ``.env`` — weder CLI-Args
  noch eine übergebene Umgebung enthalten Passwörter. ``ALLOW_BOOKING``
- wird durch den Launcher **nicht** umgeschaltet.

Ein-Schuss-Kommandos (uv sync, playwright install, git pull) streamen ihre
Ausgabe zeilenweise an eine ``log``-Callback — die GUI hängt sie ins LogView.
Der dauerhafte Server nutzt den ``SubprocessManager`` (eigener Stream).
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from core import envtool, gitops, paths
from core.process import SubprocessManager, run_streaming

# Kanonische Werte (geeint mit ausleihe-ausgabe/.env.example + start.bat).
SERVER_MODULE = "server.main"
DEFAULT_PORT = 3443
HOST_PATH = "/host"

# Beide Repos, die zusammen das ausleihe-ausgabe-Werkzeug bilden. Reihenfolge
# = Abhängigkeit: ausleihe-api zuerst (editable Install des Hauptwerkzeugs).
AUSLEIHE_REPOS: tuple[str, ...] = ("ausleihe-api", "ausleihe-ausgabe")

LogFn = Callable[[str], None]

# Hinweis, der nach install angezeigt wird (Silent-Print der Leihscheine).
# Windows-spezifisch; der Launcher installiert SumatraPDF nicht selbst, um
# kein Winget/Admin vorauszusetzen — nur ein Hand-Hinweis.
SUMATRA_HINT = (
    "Hinweis: Für den Leihschein-Druck (Silent-Print) wird SumatraPDF "
    "empfohlen. Download: https://www.sumatrapdfreader.org/ — optional, "
    "ohne SumatraPDF fällt der Druck auf den Windows-Standard zurück."
)


# Muster für den absoluten venv-Python-Pfad, den uv in Console-Scripts
# (``.venv/bin/<tool>``) bei der Erstellung reingebackt hat. uv-venvs sind
# NICHT relocatable: wird das Projektverzeichnis danach umbenannt/verschoben
# (hier: ``IServ-Ausleihe-Ausgabe`` → ``ausleihe-ausgabe``), zeigen diese
# Pfade ins Leere — jeder Console-Script-Aufruf (z. B. ``playwright``)
# scheitert mit Exit 126. ``uv sync`` fällt *nicht* darauf (nutzt den
# venv-Python direkt per Symlink), daher braucht es eine eigene Prüfung.
# POSIX: ``/…/.venv/bin/python3.12``; Windows: ``C:\…\.venv\Scripts\python.exe``.
_VENV_PY_REF = re.compile(
    r"(?:"
    r"/[^\s'\"\)]*?/\.venv/bin/python[\w.\-]*"  # POSIX
    r"|"
    r"[A-Za-z]:\\[^\s'\"\)]*?\\.venv\\Scripts\\python[\w.\-]*\.exe"  # Windows
    r")"
)


def _venv_is_stale(venv: Path) -> bool:
    """``True`` gdw. der venv Console-Scripts enthält, deren gebackter absoluter
    Python-Pfad nicht mehr existiert (Verzeichnis wurde umbenannt/verschoben).

    ``False`` für: keinen venv, venv ohne Console-Scripts, oder einen am
    aktuellen Ort korrekt funktionierenden venv (kein False-Positive bei
    frischen/aktuellen venvs — deren Referenzpfad existiert ja).
    """
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    if not bin_dir.is_dir():
        return False
    for script in bin_dir.iterdir():
        if not script.is_file():
            continue
        # Nur Text-Console-Scripts (Symlinks/Binaries überspringen). Fehler
        # beim Lesen (z. B. Permission) tolerieren wir als „nicht stale".
        try:
            head = script.read_text(errors="ignore")[:400]
        except OSError:
            continue
        m = _VENV_PY_REF.search(head)
        if m and not Path(m.group(0)).exists():
            return True
    return False


def _recreate_venv(repo: Path, log: LogFn) -> None:
    """Entfernt einen stale venv, damit ``uv sync`` ihn frisch neu anlegt.

    Nur Console-Scripts sind kaputt (der venv-Python-Symlink funktioniert
    noch). Der sauberste Weg zu korrekten Pfaden ist ein neuer venv.
    ``.env`` liegt am Repo-Root (nicht im venv) → bleibt erhalten; die
    Playwright-Browser liegen im OS-Cache (nicht im venv) → kein
    Chromium-Neudownload. ``uv sync`` holt Pakete aus dem uv-Cache (schnell).
    """
    import shutil

    log(
        f"[ausleihe-ausgabe] venv ist veraltet (Verzeichnis verschoben/"
        f"umbenannt) — wird neu erstellt: {repo / '.venv'}"
    )
    shutil.rmtree(repo / ".venv", ignore_errors=True)


def install(log: LogFn) -> None:
    """Klont beide Repos, ``uv sync``, ``playwright install chromium``.

    Idempotent: bereits installierte Repos werden nicht erneut geklont
    (Tippfehler-Schutz gegen ein Überschreiben lokaler Pflege). ``uv sync``
    und Playwright laufen immer (bringen Repos auf den aktuellen Stand).
    Hebt bei kritischem Fehler (clone/sync/playwright scheitert).
    """
    # 1. Repos klonen (ausleihe-api zuerst — Dependency des Hauptwerkzeugs).
    for name in AUSLEIHE_REPOS:
        if paths.exists(name):
            log(f"[{name}] bereits installiert — clone übersprungen")
            continue
        url = gitops.REPO_URLS[name]
        log(f"[{name}] klone {url} …")
        gitops.clone(name, url)
        log(f"[{name}] clone ok")

    # 2. uv sync im Hauptwerkzeug (bindet ../ausleihe-api als editable Install).
    aa_repo = paths.sibling("ausleihe-ausgabe")
    if _venv_is_stale(aa_repo / ".venv"):
        _recreate_venv(aa_repo, log)
    log("[ausleihe-ausgabe] uv sync …")
    rc = run_streaming(["uv", "sync"], log=log, cwd=aa_repo)
    if rc != 0:
        raise RuntimeError(f"uv sync fehlgeschlagen (Exit {rc})")

    # 3. Chromium für den Playwright-Write-Pfad (Buchung via Frontend).
    log("[ausleihe-ausgabe] playwright install chromium …")
    rc = run_streaming(
        ["uv", "run", "playwright", "install", "chromium"],
        log=log,
        cwd=paths.sibling("ausleihe-ausgabe"),
    )
    if rc != 0:
        raise RuntimeError(f"playwright install fehlgeschlagen (Exit {rc})")

    log("[ausleihe-ausgabe] Installation fertig. " + SUMATRA_HINT)


def update(log: LogFn) -> dict[str, gitops.RepoStatus]:
    """``git pull`` in beiden Repos + ``uv sync``. Liefert den Vorher-Status.

    Der Vorher-Status (inkl. ``dirty``) wird zurückgegeben, damit die GUI
    anzeigen kann, ob ein Repo lokale Änderungen hatte (pull --ff-only
    scheitert dann ggf.). Dirty ist kein Abbruchgrund — nur ein Hinweis.
    """
    pre = {name: gitops.status(name) for name in AUSLEIHE_REPOS}
    for name, st in pre.items():
        if not st.installed:
            raise FileNotFoundError(f"{name} nicht installiert — erst install() aufrufen")
        if st.dirty:
            log(f"[{name}] WARNUNG: lokale Änderungen — pull --ff-only könnte scheitern")

    for name in AUSLEIHE_REPOS:
        log(f"[{name}] git pull --ff-only …")
        out = gitops.pull(name)
        if out:
            log(out)

    log("[ausleihe-ausgabe] uv sync …")
    aa_repo = paths.sibling("ausleihe-ausgabe")
    if _venv_is_stale(aa_repo / ".venv"):
        _recreate_venv(aa_repo, log)
    rc = run_streaming(["uv", "sync"], log=log, cwd=aa_repo)
    if rc != 0:
        raise RuntimeError(f"uv sync fehlgeschlagen (Exit {rc})")

    log("Update fertig.")
    return pre


def host_url() -> str:
    """Baut die Host-URL aus ``.env`` PORT (Default 3443).

    Liest nur die ``.env`` des Hauptwerkzeugs (dort steht ``PORT``). Ist das
    Repo/die .env noch nicht da, gilt der Default-Port.
    """
    port = DEFAULT_PORT
    env = envtool.read_env(paths.env_file("ausleihe-ausgabe"))
    raw = env.get("PORT", "").strip()
    if raw:
        with contextlib.suppress(ValueError):
            port = int(raw)
    return f"https://localhost:{port}{HOST_PATH}"


def start_server(manager: SubprocessManager) -> None:
    """Startet ``uv run python -m server.main`` via ``manager`` (Subprocess).

    Der Server liest seine Credentials aus ``.env`` selbst — der Subprocess
    erbt lediglich ``os.environ`` (keine Passwörter im Kommando). Hebt, falls
    das Repo oder die ``.env`` fehlt (Vorbedingung für einen Start).
    """
    if not paths.exists("ausleihe-ausgabe"):
        raise FileNotFoundError("ausleihe-ausgabe nicht installiert — erst install()")
    env_path = paths.env_file("ausleihe-ausgabe")
    if not env_path.is_file():
        raise FileNotFoundError(".env fehlt — erst das Formular ausfüllen")
    cmd = ["uv", "run", "python", "-m", SERVER_MODULE]
    manager.start(cmd, cwd=paths.sibling("ausleihe-ausgabe"))


def stop_server(manager: SubprocessManager) -> int | None:
    """Stoppt den Server-Subprocess sauber (delegiert an ``manager.stop()``)."""
    return manager.stop()


def open_host() -> str:
    """Öffnet die Host-URL im Standard-Browser; liefert die URL zurück.

    GUI-only (Windows-Laptop). Auf dem headless VPS nicht aufrufbar —
    ``webbrowser`` ist stdlib, schlägt dort harmlos fehl.
    """
    import webbrowser

    url = host_url()
    webbrowser.open(url)
    return url
