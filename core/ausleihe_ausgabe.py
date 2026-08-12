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
import subprocess
from collections.abc import Callable
from pathlib import Path

from core import envtool, gitops, paths
from core.process import SubprocessManager

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


def _run_streaming(
    cmd: list[str],
    log: LogFn,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 600.0,
) -> int:
    """Führt ein Ein-Schuss-Kommando aus, streamt stdout+stderr nach ``log``.

    Liefert den Exit-Code. Kein ``raise`` — Aufrufer prüft auf ``!= 0`` und
    erzeugt eine klare Fehlermeldung (mit Kommando + Exit-Code).
    """
    log(f"$ {' '.join(cmd)}")
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if env is not None:
        kwargs["env"] = env
    proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, **kwargs)
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\n"))
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        log(f"[Zeitüberschreitung nach {timeout}s — Prozess gekillt]")
    return proc.returncode


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
    log("[ausleihe-ausgabe] uv sync …")
    rc = _run_streaming(["uv", "sync"], log=log, cwd=paths.sibling("ausleihe-ausgabe"))
    if rc != 0:
        raise RuntimeError(f"uv sync fehlgeschlagen (Exit {rc})")

    # 3. Chromium für den Playwright-Write-Pfad (Buchung via Frontend).
    log("[ausleihe-ausgabe] playwright install chromium …")
    rc = _run_streaming(
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
    rc = _run_streaming(["uv", "sync"], log=log, cwd=paths.sibling("ausleihe-ausgabe"))
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
