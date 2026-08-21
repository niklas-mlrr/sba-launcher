"""Orchestrierung der Bestand-/Nachbestellungs-Excel (install/update/run_auto).

Das Bestand-Werkzeug ist ein Ein-Schuss-Skript im sba-bestand-Repo:

    sba-bestand/bestand/update_bestand_auto.py

Es liest die Excel-Struktur selbst aus, zieht Bestands-/Anmeldezahlen per
IServ-GET und trägt sie in die Excel ein (bzw. nur im ``--dry-run`` auf stdout).
``run_auto`` shellt dieses Skript in einem **eigenen Venv** (openpyxl, isbnlib,
python-dotenv, reportlab) und streamt stdout als Report ins LogView.

Venv-Strategie (O2, entschieden 2026-08-12; angepasst 2026-08-21): eigenes
isoliertes ``.venv-bestand`` im sba-bestand-Root via ``uv venv`` +
``uv pip install -e .`` — kein globales pip, getrennt vom Launcher- und
ausleihe-ausgabe-Venv. Spiegelt das Barcode-Client-Venv-Pattern
(``core/barcode.py``).

Unabhängigkeit (O4, revidiert 2026-08-21): ``install`` klont **zwei** Repos —
``sba-bestand`` (die Skripte) und ``ausleihe-api`` (der Client ``ausleihe`` +
die ``.env`` mit den Credentials). Vor der Extraktion am 2026-08-21 lagen die
Skripte in ``ausleihe-api``, daher genügte damals ein Repo. Der Bestand-Tab
bleibt weiterhin unabhängig von ``ausleihe-ausgabe``.

Produktionsschutz (CLAUDE.md):
- ``update_bestand_auto.py`` macht **nur GET**-Zugriffe auf die IServ-API und
  schreibt ausschließlich in die lokale Excel-Datei — nie nach IServ.
- ``ALLOW_BOOKING`` wird nicht angetastet; API-Writes werden nicht angeboten.
- Credentials stehen weiterhin in ``ausleihe-api/.env``; das Skript liest sie
  via ``python-dotenv`` selbst aus dem Geschwister-Repo
  (``load_dotenv(_API_ROOT / ".env")``). Der Launcher
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

# Relativer Pfad zum Bestand-Skript-Verzeichnis (vom sba-bestand-Root aus).
# Seit 2026-08-21 ASCII ohne Leerzeichen (vorher "bestand- und
# nachbestellungen/New - API approach"); CLI-Args werden weiterhin als Liste
# (nicht shell) gereicht, daher kein Quoting nötig.
BESTAND_DIR_REL = Path("bestand")
BESTAND_SCRIPT_REL = BESTAND_DIR_REL / "update_bestand_auto.py"
BESTAND_CONFIG_REL = BESTAND_DIR_REL / "config.json"

# Eigenes Venv für die Bestand-Abhängigkeiten (O2). Liegt im sba-bestand-Root;
# ``.venv*`` ist dort konventionsgemäß gitignored.
BESTAND_VENV_DIR = Path(".venv-bestand")

# sba-bestand hat keine Extras mehr — die Abhängigkeiten (openpyxl, isbnlib,
# python-dotenv, reportlab) stehen direkt in sba-bestand/pyproject.toml, das
# ausleihe-api als editable-Pfad-Quelle einbindet.

LogFn = Callable[[str], None]


# --- Pfad-Helfer ----------------------------------------------------------


def bestand_root() -> Path:
    """Wurzel des sba-bestand-Repos (``../sba-bestand``)."""
    return paths.sibling("sba-bestand")


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
    """``ausleihe-api/.env`` — dort liest das Skript die IServ-Credentials.

    Bewusst **nicht** ``sba-bestand/.env``: sba-bestand hält keine eigenen
    Secrets, sondern liest die ``.env`` des Geschwister-Repos (siehe
    ``sba-bestand/README.md``).
    """
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
    """Klont ``sba-bestand`` + ``ausleihe-api`` (idempotent) + legt das Venv an.

    O4 (revidiert 2026-08-21): klont **beide** Repos — die Skripte liegen in
    ``sba-bestand``, der Client ``ausleihe`` und die ``.env`` in
    ``ausleihe-api``. Weiterhin unabhängig von ausleihe-ausgabe. Danach
    ``uv venv`` + ``uv pip install -e .`` im sba-bestand-Root. Hebt bei
    kritischem Fehler (clone/venv scheitert). Hinweis, falls die ``.env``
    noch fehlt (das Skript braucht IServ-Credentials).
    """
    # 1. Repos klonen (idempotent — nicht zweimal klonen).
    #    Reihenfolge: ausleihe-api zuerst, damit der editable-Pfad-Install
    #    von sba-bestand (``../ausleihe-api``) sein Ziel bereits vorfindet.
    for repo in ("ausleihe-api", "sba-bestand"):
        if paths.exists(repo):
            log(f"[{repo}] bereits installiert — clone übersprungen")
            continue
        url = gitops.REPO_URLS[repo]
        log(f"[{repo}] klone {url} …")
        gitops.clone(repo, url)
        log(f"[{repo}] clone ok")

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
    """``git pull`` in sba-bestand + ausleihe-api, dann Venv auffrischen.

    Liefert den Vorher-Status von ``sba-bestand`` (inkl. ``dirty``), damit die
    GUI warnen kann, falls ``pull --ff-only`` wegen lokaler Änderungen
    scheitert. Das Venv wird neu installiert (``-e`` editable — Code-Änderungen
    in beiden Repos werden sofort gezogen).
    """
    pre = gitops.status("sba-bestand")
    if not pre.installed:
        raise FileNotFoundError("sba-bestand nicht installiert — erst install()")

    for repo in ("ausleihe-api", "sba-bestand"):
        st = gitops.status(repo)
        if not st.installed:
            raise FileNotFoundError(f"{repo} nicht installiert — erst install()")
        if st.dirty:
            log(f"[{repo}] WARNUNG: lokale Änderungen — pull --ff-only könnte scheitern")
        log(f"[{repo}] git pull --ff-only …")
        out = gitops.pull(repo)
        if out:
            log(out)

    _ensure_bestand_venv(log)

    log("Update fertig.")
    return pre


def _ensure_bestand_venv(log: LogFn) -> None:
    """Legt das Bestand-Venv an und installiert ``-e .`` (sba-bestand).

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
    log("[bestand] uv pip install -e . …")
    rc = run_streaming(
        ["uv", "pip", "install", "--python", str(venv_python), "-e", "."],
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

    Vorbedingung: sba-bestand **und** ausleihe-api installiert + Bestand-Venv
    vorhanden + Skript da. ausleihe-api wird gebraucht, weil das Skript von dort
    den Client ``ausleihe`` und die ``.env`` zieht. Hebt mit klaren Fehlern,
    falls eine Vorbedingung fehlt (GUI zeigt sie).
    """
    if log is None:
        log = lambda _l: None  # noqa: E731 — Default-Noop

    for repo in ("sba-bestand", "ausleihe-api"):
        if not paths.exists(repo):
            raise FileNotFoundError(f"{repo} nicht installiert — erst install()")
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
