"""Orchestrierung der Bestand-/Nachbestellungs-Excel (install/update/run_auto).

Das Bestand-Werkzeug ist ein Ein-Schuss-Skript im ausleihe-api-Repo:

    ausleihe-api/bestand- und nachbestellungen/New - API approach/update_bestand_auto.py

Es liest die Excel-Struktur selbst aus, zieht Bestands-/Anmeldezahlen per
IServ-GET und trägt sie in die Excel ein (bzw. nur im ``--dry-run`` auf stdout).
``run_auto`` shellt dieses Skript in einem **eigenen Venv** (``.[bestand]``-Extra:
openpyxl, isbnlib, python-dotenv) und streamt stdout als Report ins LogView.

Venv-Strategie (O2, entschieden 2026-08-12): eigenes isoliertes ``.venv-bestand``
im ausleihe-api-Root via ``uv venv`` + ``uv pip install -e ".[bestand]"`` — kein
globales pip, getrennt vom Launcher- und ausleihe-ausgabe-Venv. Spiegelt das
Barcode-Client-Venv-Pattern (``core/barcode.py``).

Unabhängigkeit (O4): ``install`` klont **nur** ``ausleihe-api`` — der Bestand-Tab
bleibt nutzbar, auch wenn ``ausleihe-ausgabe`` (noch) nicht installiert ist.

Produktionsschutz (CLAUDE.md):
- ``update_bestand_auto.py`` macht **nur GET**-Zugriffe auf die IServ-API und
  schreibt ausschließlich in die lokale Excel-Datei — nie nach IServ.
- ``ALLOW_BOOKING`` wird nicht angetastet; API-Writes werden nicht angeboten.
- Credentials stehen in ``ausleihe-api/.env``; das Skript liest sie via
  ``python-dotenv`` selbst (``load_dotenv(_ROOT / ".env")``). Der Launcher
  reicht **keine** Passwörter als CLI-Args — der Subprocess erbt lediglich
  ``os.environ`` (damit ``uv``/Python funktionieren).

tkinter-frei — auf dem headless VPS via pytest testbar (Pfade + Kommando-Bau
gegen ein tmp-Repo; ``run_auto`` gegen einen gemockten ``run_streaming``).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from core import gitops, paths
from core.process import run_streaming

# Relativer Pfad zum Bestand-Skript-Verzeichnis (vom ausleihe-api-Root aus).
# Mit Leerzeichen/Umlauten — pathlib handhabt das; CLI-Args werden als Liste
# (nicht shell) gereicht, daher kein Quoting nötig.
BESTAND_DIR_REL = Path("bestand- und nachbestellungen/New - API approach")
BESTAND_SCRIPT_REL = BESTAND_DIR_REL / "update_bestand_auto.py"
BESTAND_CONFIG_REL = BESTAND_DIR_REL / "config.json"

# Eigenes Venv für das Bestand-Extra (O2). Liegt im ausleihe-api-Root;
# ``.venv*`` ist dort konventionsgemäß gitignored.
BESTAND_VENV_DIR = Path(".venv-bestand")

# Extra, das die Bestand-Abhängigkeiten (openpyxl, isbnlib, python-dotenv)
# zieht — definiert in ausleihe-api/pyproject.toml.
BESTAND_EXTRA = "bestand"

LogFn = Callable[[str], None]


# --- Pfad-Helfer ----------------------------------------------------------


def bestand_root() -> Path:
    """Wurzel des ausleihe-api-Repos (``../ausleihe-api``)."""
    return paths.sibling("ausleihe-api")


def bestand_dir() -> Path:
    """Verzeichnis mit ``update_bestand_auto.py`` + ``config.json``."""
    return bestand_root() / BESTAND_DIR_REL


def script_path() -> Path:
    """Pfad von ``update_bestand_auto.py`` (auch wenn noch nicht geklont)."""
    return bestand_root() / BESTAND_SCRIPT_REL


def config_path() -> Path:
    """Pfad der Bestand-``config.json`` (auch wenn noch nicht geklont)."""
    return bestand_root() / BESTAND_CONFIG_REL


def env_file() -> Path:
    """``ausleihe-api/.env`` — dort liest das Skript die IServ-Credentials."""
    return paths.env_file("ausleihe-api")


def venv_python_rel(os_name: str | None = None) -> Path:
    """Relativer Pfad zum Venv-Interpreter je Plattform (wie barcode).

    Ausgelagert, damit der Plattform-Zweig ohne Patchen von ``os.name`` testbar
    ist (``os_name``-Parameter).
    """
    if (os_name if os_name is not None else os.name) == "nt":
        return Path("Scripts") / "python.exe"
    return Path("bin") / "python"


def bestand_venv_python() -> Path:
    """Pfad zum Interpreter des Bestand-Venvs (ohne Existenzprüfung).

    Kreuz-Plattform: Windows ``Scripts/python.exe``, POSIX ``bin/python``.
    """
    return bestand_root() / BESTAND_VENV_DIR / venv_python_rel()


def bestand_venv_dir() -> Path:
    """Absoluter Pfad des Bestand-Venv-Verzeichnisses."""
    return bestand_root() / BESTAND_VENV_DIR


# --- Install / Update -----------------------------------------------------


def install(log: LogFn) -> None:
    """Klont ``ausleihe-api`` (idempotent) + legt das Bestand-Venv an.

    O4: klont **nur** ausleihe-api — unabhängig von ausleihe-ausgabe. Danach
    ``uv venv`` + ``uv pip install -e ".[bestand]"`` im ausleihe-api-Root. Hebt
    bei kritischem Fehler (clone/venv scheitert). Hinweis, falls die ``.env``
    noch fehlt (das Skript braucht IServ-Credentials).
    """
    # 1. Repo klonen (idempotent — nicht zweimal klonen).
    if paths.exists("ausleihe-api"):
        log("[ausleihe-api] bereits installiert — clone übersprungen")
    else:
        url = gitops.REPO_URLS["ausleihe-api"]
        log(f"[ausleihe-api] klone {url} …")
        gitops.clone("ausleihe-api", url)
        log("[ausleihe-api] clone ok")

    # 2. Bestand-Venv (openpyxl, isbnlib, python-dotenv isoliert).
    _ensure_bestand_venv(log)

    # 3. .env-Hinweis (Credentials werden über das zentrale Form geschrieben).
    if not env_file().is_file():
        log(
            "[ausleihe-api] Hinweis: .env fehlt — im Tab 'Ausleihe-Ausgabe' das "
            "Formular ausfüllen (ISERV_*); Bestand braucht dieselben Credentials."
        )

    log("[bestand] Installation fertig.")


def update(log: LogFn) -> gitops.RepoStatus:
    """``git pull`` in ausleihe-api + Bestand-Venv auffrischen.

    Liefert den Vorher-Status (inkl. ``dirty``), damit die GUI warnen kann,
    falls ``pull --ff-only`` wegen lokaler Änderungen scheitert. Das Venv wird
    neu installiert (``-e`` editable — Code-Änderungen werden sofort gezogen).
    """
    pre = gitops.status("ausleihe-api")
    if not pre.installed:
        raise FileNotFoundError("ausleihe-api nicht installiert — erst install()")
    if pre.dirty:
        log("[ausleihe-api] WARNUNG: lokale Änderungen — pull --ff-only könnte scheitern")

    log("[ausleihe-api] git pull --ff-only …")
    out = gitops.pull("ausleihe-api")
    if out:
        log(out)

    _ensure_bestand_venv(log)

    log("Update fertig.")
    return pre


def _ensure_bestand_venv(log: LogFn) -> None:
    """Legt das Bestand-Venv an und installiert ``-e ".[bestand]"``.

    Idempotent: ``uv pip install`` läuft immer (bringt das editable-Paket + Extra
    auf Stand). ``uv venv`` aktualisiert ein bestehendes Venv nicht, wird daher
    nur bei fehlendem Interpreter ausgeführt.
    """
    venv_python = bestand_venv_python()
    venv_dir = bestand_venv_dir()
    if not venv_python.is_file():
        log("[bestand] uv venv (.venv-bestand) …")
        rc = run_streaming(["uv", "venv", str(venv_dir)], log=log, cwd=bestand_root())
        if rc != 0:
            raise RuntimeError(f"uv venv fehlgeschlagen (Exit {rc})")
    log(f"[bestand] uv pip install -e .[{BESTAND_EXTRA}] …")
    rc = run_streaming(
        ["uv", "pip", "install", "--python", str(venv_python), "-e", f".[{BESTAND_EXTRA}]"],
        log=log,
        cwd=bestand_root(),
    )
    if rc != 0:
        raise RuntimeError(f"uv pip install fehlgeschlagen (Exit {rc})")


# --- run_auto (Ein-Schuss, streamed) ---------------------------------------


def build_cmd(
    dry_run: bool,
    excel: Path | str | None,
    schoolyear: str | None = None,
    safety_stock: int | None = None,
) -> list[str]:
    """Baut das Kommando für ``update_bestand_auto.py`` (ohne Interpreter-Prefix).

    ``excel`` wird absolut gereicht (pathlib: ``_HERE / "/abs"`` == ``/abs``),
    damit das Skript eine beliebig gewählte Excel-Datei findet — nicht nur eine
    neben dem Skript liegende. ``dry_run`` setzt ``--dry-run`` (schreibt nicht).
    """
    cmd: list[str] = ["-v"]
    if dry_run:
        cmd.append("--dry-run")
    if excel is not None:
        cmd += ["--excel", str(Path(excel).resolve())]
    if schoolyear:
        cmd += ["--schoolyear", schoolyear]
    if safety_stock is not None:
        cmd += ["--safety-stock", str(safety_stock)]
    return cmd


def run_auto(
    dry_run: bool,
    excel: Path | str | None = None,
    schoolyear: str | None = None,
    log: LogFn | None = None,
    safety_stock: int | None = None,
) -> int:
    """Führt ``update_bestand_auto.py`` im Bestand-Venv aus; liefert Exit-Code.

    Streamt stdout+stderr zeilenweise an ``log`` (der Report im LogView). Das
    Skript liest seine IServ-Credentials aus ``ausleihe-api/.env`` selbst — der
    Subprocess erbt ``os.environ`` (keine Passwörter im Kommando).

    Vorbedingung: ausleihe-api installiert + Bestand-Venv vorhanden + Skript da.
    Hebt mit klaren Fehlern, falls eine Vorbedingung fehlt (GUI zeigt sie).
    """
    if log is None:
        log = lambda _l: None  # noqa: E731 — Default-Noop

    if not paths.exists("ausleihe-api"):
        raise FileNotFoundError("ausleihe-api nicht installiert — erst install()")
    script = script_path()
    if not script.is_file():
        raise FileNotFoundError(
            f"Bestand-Skript fehlt: {script} — erst update() oder install()"
        )
    venv_python = bestand_venv_python()
    if not venv_python.is_file():
        raise FileNotFoundError(
            f"Bestand-Venv fehlt ({venv_python}) — erst install() aufrufen"
        )
    if not env_file().is_file():
        raise FileNotFoundError(
            "ausleihe-api/.env fehlt — im Tab 'Ausleihe-Ausgabe' das Formular "
            "ausfüllen (Bestand braucht dieselben IServ-Credentials)."
        )

    cmd = [str(venv_python), str(script), *build_cmd(dry_run, excel, schoolyear, safety_stock)]
    mode = "DRY RUN" if dry_run else "ECHT (schreibt in die Excel)"
    log(f"[bestand] {mode} — starte update_bestand_auto.py …")
    rc = run_streaming(cmd, log=log, cwd=bestand_dir())
    log(f"[bestand] beendet — Exit-Code {rc}")
    return rc
