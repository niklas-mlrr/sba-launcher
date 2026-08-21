"""Orchestrierung des eigenständigen Barcode-Scanners (install/update/start/stop).

Der Barcode-Scanner ist ein Zwei-Prozess-Stack (``barcode-scanner-simple``):

- **Server** (Node.js): ``node server/server.js`` — HTTPS + WebSocket-Bridge.
  Schreibt beim Start ``server/runtime/session.json`` (Port, certPath,
  ``desktopToken``) und gibt die Scanner-URL (``#s=<scannerToken>``) als
  ASCII-QR **und** als Klartext-Zeile ``Scanner URL: …`` auf stdout aus.
- **Client** (Python): ``python client/client.py --session-file …`` — verbindet
  sich mit dem lokalen Server und tippt gescannte Barcodes als Tastatur.

Dieser Modul verbindet :mod:`gitops` (clone/pull), :mod:`prereqs` (portables
Node), :mod:`process` (SubprocessManager + :func:`run_streaming`) zu den
vier Tab-Aktionen. tkinter-frei — auf dem headless VPS via pytest testbar
(start/stop mit Fake-Managern, kein echtes Node/pyautogui).

Produktionsschutz (CLAUDE.md): Barcode hat keinen IServ-Kontakt — es ist ein
reiner Browser→Tastatur-Bridge. Dennoch werden keine Credentials geloggt; der
Client erhält seine Authentifizierung aus der lokalen ``session.json``, nicht
über CLI-Args (außer dem Dateipfad, der kein Secret enthält).

QR-View: die Scanner-URL wird aus dem Server-stdout geparst
(:func:`parse_scanner_url`), da ``session.json`` nur das ``desktopToken``
enthält, nicht den ``scannerToken`` (siehe Barcode-Repo ``server.js``).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

from core import gitops, paths, prereqs
from core.process import SubprocessManager, run_streaming

# Kanonische Werte (geeint mit barcode-scanner-simple/start.bat + server.js).
SERVER_PORT_DEFAULT = 3443
# Relative Pfade innerhalb des barcode-scanner-simple-Repos (vom Repo-Root aus).
SERVER_SCRIPT = Path("server/server.js")
CLIENT_SCRIPT = Path("client/client.py")
CLIENT_REQUIREMENTS = Path("client/requirements.txt")
SESSION_REL = Path("server/runtime/session.json")
# Wie lange auf session.json gewartet wird, nachdem der Server gestartet ist
# (start.bat pollt 25×1s; wir geben etwas Luft).
SESSION_TIMEOUT_S = 30.0
SESSION_POLL_INTERVAL_S = 0.25
# Venv für den Python-Client (eigene Umgebung, damit pyautogui/pynput/websocket
# isoliert vom Launcher installiert werden). Liegt im Repo-Root; .venv* ist in
# barcode-scanner-simple/.gitignore konventionsgemäß ignoriert.
CLIENT_VENV_DIR = Path(".venv-client")

LogFn = Callable[[str], None]

# Scanner-URL aus der Klartext-Zeile ``Scanner URL: <url>`` extrahieren.
# Die URL trägt das ``#s=…``-Fragment (scannerToken); siehe server.js.
_SCANNER_URL_RE = re.compile(r"Scanner URL:\s*(https?://\S+)")


# --- Pfad-Helfer ----------------------------------------------------------


def barcode_root() -> Path:
    """Wurzel des barcode-scanner-simple-Repos (``../barcode-scanner-simple``)."""
    return paths.sibling("barcode-scanner-simple")


def session_file() -> Path:
    """Pfad von ``server/runtime/session.json`` (auch wenn noch nicht da)."""
    return barcode_root() / SESSION_REL


def server_dir() -> Path:
    """``barcode-scanner-simple/server`` ( cwd für ``npm install``)."""
    return barcode_root() / "server"


def venv_python_rel(os_name: str | None = None) -> Path:
    """Relativer Pfad zum Venv-Python-Interpreter je Plattform.

    Windows: ``Scripts/python.exe``; POSIX: ``bin/python``. Ausgelagert als
    reine Funktion, damit der Plattform-Zweig ohne Patchen des globalen
    ``os.name`` testbar ist (``os_name``-Parameter statt ``os.name``-Lesen).
    """
    if (os_name if os_name is not None else os.name) == "nt":
        return Path("Scripts") / "python.exe"
    return Path("bin") / "python"


def client_venv_python() -> Path:
    """Pfad zum Python-Interpreter des Client-Venvs (ohne Existenzprüfung).

    Kreuz-Plattform: Windows legt ``Scripts/python.exe``, POSIX ``bin/python``.
    Existenz prüft der Aufrufer (start hebt, falls das Venv fehlt).
    """
    return barcode_root() / CLIENT_VENV_DIR / venv_python_rel()


# --- session.json + Scanner-URL -------------------------------------------


def read_session() -> dict | None:
    """Liest ``session.json``; ``None``, falls sie fehlt oder kaputt ist.

    Robust: der Server schreibt sie atomar (tmp+rename); ein halbfertiger Stand
    ist nicht zu erwarten, aber ein nicht-laufender Server lässt sie
    weg. Inhalt: ``{v, port, certPath, desktopToken}``.
    """
    p = session_file()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def parse_scanner_url(line: str) -> str | None:
    """Extrahiert die Scanner-URL aus einer Server-stdout-Zeile.

    Matcht ``Scanner URL: https://<ip>:<port>/#s=<token>``. Liefert ``None``
    für alle anderen Zeilen (auch die ASCII-QR-Art-Zeilen) — so kann der
    Aufrufer jede Log-Zeile füttern, ohne vorzufiltern.
    """
    m = _SCANNER_URL_RE.search(line)
    return m.group(1) if m else None


# --- Install / Update -----------------------------------------------------


def install(log: LogFn) -> None:
    """Klont barcode-scanner-simple, ``npm install`` (server), Client-Venv + Node.

    Schritte: clone (idempotent) → portables Node sicherstellen →
    ``npm install`` im server/ → ``uv venv`` + ``uv pip install`` für den
    Client. Hebt bei kritischem Fehler (clone/npm/venv scheitert).
    """
    # 1. Repo klonen (idempotent — nicht zweimal klonen).
    if paths.exists("barcode-scanner-simple"):
        log("[barcode-scanner-simple] bereits installiert — clone übersprungen")
    else:
        url = gitops.REPO_URLS["barcode-scanner-simple"]
        log(f"[barcode-scanner-simple] klone {url} …")
        gitops.clone("barcode-scanner-simple", url)
        log("[barcode-scanner-simple] clone ok")

    # 2. Portables Node sicherstellen (Barcode braucht node+npm).
    log("[barcode-scanner-simple] Node.js prüfen …")
    log(prereqs.ensure_node(log))

    # 3. npm install im server/ (Server-Abhängigkeiten: ws, selfsigned, qrcode).
    log("[barcode-scanner-simple] npm install (server) …")
    env = prereqs.node_env()
    npm = prereqs.npm_bin()
    # List form ohne shell=True: npm_bin() liefert auf Windows den vollen Pfad
    # zur npm.cmd (via shutil.which + PATHEXT); CreateProcess führt .cmd direkt
    # aus. Auf POSIX ist npm ein normales Skript.
    rc = run_streaming([npm, "install"], log=log, cwd=server_dir(), env=env)
    if rc != 0:
        raise RuntimeError(f"npm install fehlgeschlagen (Exit {rc})")

    # 4. Client-Venv (pyautogui, pynput, websocket-client isoliert).
    _ensure_client_venv(log)

    log("[barcode-scanner-simple] Installation fertig.")


def update(log: LogFn) -> gitops.RepoStatus:
    """``git pull`` + ``npm install`` + Client-Venv auffrischen.

    Liefert den Vorher-Status (inkl. ``dirty``), damit die GUI warnen kann,
    falls ``pull --ff-only`` wegen lokaler Änderungen scheitert.
    """
    pre = gitops.status("barcode-scanner-simple")
    if not pre.installed:
        raise FileNotFoundError("barcode-scanner-simple nicht installiert — erst install()")
    if pre.dirty:
        log("[barcode-scanner-simple] WARNUNG: lokale Änderungen — pull --ff-only könnte scheitern")

    log("[barcode-scanner-simple] git pull --ff-only …")
    out = gitops.pull("barcode-scanner-simple")
    if out:
        log(out)

    # Node + Server-Abhängigkeiten auffrischen.
    log(prereqs.ensure_node(log))
    env = prereqs.node_env()
    npm = prereqs.npm_bin()
    log("[barcode-scanner-simple] npm install (server) …")
    rc = run_streaming([npm, "install"], log=log, cwd=server_dir(), env=env)
    if rc != 0:
        raise RuntimeError(f"npm install fehlgeschlagen (Exit {rc})")

    # Client-Venv auffrischen (requirements könnten sich geändert haben).
    _ensure_client_venv(log)

    log("Update fertig.")
    return pre


def _ensure_client_venv(log: LogFn) -> None:
    """Legt das Client-Venv an und installiert ``client/requirements.txt``.

    Idempotent: ``uv venv`` aktualisiert ein bestehendes Venv nicht, aber
    ``uv pip install`` läuft immer (bringt die Abhängigkeiten auf Stand).
    """
    venv_python = client_venv_python()
    venv_dir = barcode_root() / CLIENT_VENV_DIR
    if not venv_python.is_file():
        log("[barcode-scanner-simple] uv venv (client) …")
        rc = run_streaming(["uv", "venv", str(venv_dir)], log=log, cwd=barcode_root())
        if rc != 0:
            raise RuntimeError(f"uv venv fehlgeschlagen (Exit {rc})")
    req = barcode_root() / CLIENT_REQUIREMENTS
    log(f"[barcode-scanner-simple] uv pip install -r {CLIENT_REQUIREMENTS} …")
    rc = run_streaming(
        ["uv", "pip", "install", "--python", str(venv_python), "-r", str(req)],
        log=log,
        cwd=barcode_root(),
    )
    if rc != 0:
        raise RuntimeError(f"uv pip install fehlgeschlagen (Exit {rc})")


# --- Start / Stop ---------------------------------------------------------


def start(server_mgr: SubprocessManager, client_mgr: SubprocessManager, log: LogFn) -> None:
    """Startet Server (node) und danach den Client (python) — zwei Subprozesse.

    Reihenfolge (wie ``barcode-scanner-simple/start.bat``): alte ``session.json``
    löschen → Server starten → auf ``session.json`` warten → Client starten.
    Der Client braucht die session.json (enthält ``desktopToken`` + certPath).

    Diese Funktion blockiert bis zu :data:`SESSION_TIMEOUT_S` s (Warten auf
    session.json) — die GUI ruft sie daher in einem Hintergrund-Thread auf.
    """
    if not paths.exists("barcode-scanner-simple"):
        raise FileNotFoundError("barcode-scanner-simple nicht installiert — erst install()")

    node = prereqs.node_bin()
    if not node:
        raise FileNotFoundError("Node.js fehlt — erst install() (ensure_node)")

    venv_python = client_venv_python()
    if not venv_python.is_file():
        raise FileNotFoundError(
            f"Client-Venv fehlt ({venv_python}) — erst install() aufrufen"
        )

    # 1. Alte session.json löschen (stale Token vom vorigen Lauf vermeiden).
    sf = session_file()
    if sf.is_file():
        sf.unlink()
        log("[barcode-scanner-simple] alte session.json entfernt")

    # 2. Server starten. cwd = Repo-Root (wie start.bat: ``node server\server.js``);
    #    server.js löst seine Pfade über __dirname, cwd spielt keine Rolle.
    env = prereqs.node_env()
    log("[barcode-scanner-simple] starte Server (node server/server.js) …")
    server_mgr.start([node, str(SERVER_SCRIPT)], cwd=barcode_root(), env=env)

    # 3. Auf session.json warten (Server schreibt sie beim listen).
    if not _wait_for_session(sf, log):
        server_mgr.stop()
        raise RuntimeError(
            f"session.json wurde nach {SESSION_TIMEOUT_S:.0f}s nicht erzeugt "
            "— Server nicht hochgekommen? Siehe Log."
        )
    log(f"[barcode-scanner-simple] session.json da: {sf}")

    # 4. Client starten. --session-file als absoluter Pfad (client.py nimmt Path).
    log("[barcode-scanner-simple] starte Client (python client/client.py) …")
    try:
        client_mgr.start(
            [str(venv_python), str(CLIENT_SCRIPT), "--session-file", str(sf)],
            cwd=barcode_root(),
        )
    except Exception:
        # Client-Start gescheitert (z. B. kaputtes Repo, CLIENT_SCRIPT fehlt) —
        # Server nicht verwaist zurücklassen (hält sonst Port + TLS-Zertifikat).
        server_mgr.stop()
        raise


def _wait_for_session(sf: Path, log: LogFn) -> bool:
    """Pollt bis zu :data:`SESSION_TIMEOUT_S` s auf das Erscheinen von ``sf``."""
    deadline = time.monotonic() + SESSION_TIMEOUT_S
    while time.monotonic() < deadline:
        if sf.is_file():
            return True
        time.sleep(SESSION_POLL_INTERVAL_S)
    return False


def stop(
    server_mgr: SubprocessManager,
    client_mgr: SubprocessManager,
    log: LogFn | None = None,
) -> dict[str, int | None]:
    """Stoppt beide Subprozesse und räumt ``session.json`` auf.

    Reihenfolge: Client zuerst (er tippt ggf. noch — sauber abbrechen), dann
    Server. Liefert die Exit-Codes ``{"client": …, "server": …}``.
    """
    client_code = client_mgr.stop()
    server_code = server_mgr.stop()
    sf = session_file()
    if sf.is_file():
        sf.unlink()
        if log is not None:
            log("[barcode-scanner-simple] session.json aufgeräumt")
    return {"client": client_code, "server": server_code}
