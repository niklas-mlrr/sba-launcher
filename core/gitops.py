"""Git-Operationen für die Geschwister-Repos (clone/pull/status + dirty-Check).

Alle Funktionen laufen über ``paths.sibling(name)`` und sind tkinter-frei —
auf dem headless VPS via pytest testbar. Für Tests wird
``paths.launcher_root`` auf ein ``tmp_path`` gebogen; clone-Quellen sind dann
lokale Dateipfade (bare repos), nicht GitHub.

Produktionsschutz (CLAUDE.md): ``git pull`` ist reines Lesen, es werden keine
Remote-Schreibzugriffe (push) angeboten.

Defensiv: fehlt das Repo, liefern ``status``/``is_dirty`` klare Ergebnisse
(installed=False, dirty=False) statt zu craschen; ``pull``/``clone`` heben
mit aussagekräftigen Fehlern.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import paths

# Kanonische Remote-URLs (GitHub HTTPS, public). Werden für clone verwendet;
# der Launcher pusht nie (Produktionsschutz).
REPO_URLS: dict[str, str] = {
    "ausleihe-ausgabe": "https://github.com/niklas-mlrr/IServ-Ausleihe-Ausgabe.git",
    "ausleihe-api": "https://github.com/niklas-mlrr/IServ-Ausleihe-API.git",
    "barcode-simple": "https://github.com/niklas-mlrr/Barcode-Scanner.git",
}

# Timeouts: status ist lokal schnell; clone/pull gehen ins Netz.
_TIMEOUT_FAST = 30
_TIMEOUT_NET = 300


@dataclass(frozen=True)
class RepoStatus:
    """Status-Abbildung eines Geschwister-Repos für die GUI.

    ``installed`` = Repo mit ``.git`` vorhanden. ``branch`` ist der
    abgekürzte Ref (``main``) oder ``None``. ``dirty`` = uncommitted Changes
    (``git status --porcelain`` nicht leer). ``error`` = Git-Fehlermeldung,
    falls ein Kommando scheiterte (sonst ``None``).
    """

    name: str
    path: Path
    installed: bool
    branch: str | None
    dirty: bool
    error: str | None

    def __str__(self) -> str:
        if not self.installed:
            return f"{self.name}: nicht installiert"
        parts = [f"{self.name}: {self.branch or '(detached)'}"]
        parts.append("dirty" if self.dirty else "clean")
        if self.error:
            parts.append(f"FEHLER: {self.error}")
        return " | ".join(parts)


def _run(
    args: list[str], cwd: Path, timeout: int = _TIMEOUT_FAST
) -> subprocess.CompletedProcess[str]:
    """Führt ein Git-Kommando aus; liefert CompletedProcess (check=False).

    ``cwd`` muss existieren (Aufrufer sorgt dafür).
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _git_ok(proc: subprocess.CompletedProcess[str]) -> bool:
    return proc.returncode == 0


def status(name: str) -> RepoStatus:
    """Liefert den Repo-Status (installiert, Branch, dirty).

    Nicht-installierte Repos sind ein legitimer Zustand (vor dem Klonen) —
    liefert ``installed=False`` ohne Fehler.
    """
    path = paths.sibling(name)
    if not paths.exists(name):
        return RepoStatus(name, path, installed=False, branch=None, dirty=False, error=None)

    branch_proc = _run(["rev-parse", "--abbrev-ref", "HEAD"], path)
    dirty_proc = _run(["status", "--porcelain"], path)

    error: str | None = None
    if not _git_ok(branch_proc):
        error = branch_proc.stderr or branch_proc.stdout or "rev-parse fehlgeschlagen"
    elif not _git_ok(dirty_proc):
        error = dirty_proc.stderr or dirty_proc.stdout or "status fehlgeschlagen"

    branch = branch_proc.stdout.strip() or None
    dirty = bool(dirty_proc.stdout.strip())
    return RepoStatus(name, path, installed=True, branch=branch, dirty=dirty, error=error)


def is_dirty(name: str) -> bool:
    """``True`` gdw. Repo installiert ist und uncommitted Changes enthält."""
    return status(name).dirty


def clone(name: str, url: str | None = None) -> Path:
    """Klont ``url`` nach ``sibling(name)``. Liefert den Zielpfad.

    ``url`` defaultet auf :data:`REPO_URLS` (kanonische GitHub-URL). Für Tests
    wird ein lokaler Dateipfad (bare repo) übergeben.

    Hebt ``FileExistsError``, falls das Ziel bereits nicht-leer existiert —
    verhindert versehentliches Überschreiben eines gepflegten Repos.
    """
    if url is None:
        url = REPO_URLS[name]
    target = paths.sibling(name)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Ziel existiert und ist nicht leer: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    proc = _run(["clone", "--", url, str(target)], cwd=target.parent, timeout=_TIMEOUT_NET)
    if not _git_ok(proc):
        # Aufräumen eines halben Klons (git legt ggf. ein Verzeichnis an).
        if target.exists():
            # Kein shutil.rmtree im core (keine Import-Beschränkung, aber
            # defensiv: nur entfernen, was .git enthält).
            import shutil

            shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(
            f"clone fehlgeschlagen für {name}: {proc.stderr or proc.stdout or 'unbekannt'}"
        )
    return target


def pull(name: str) -> str:
    """``git pull --ff-only`` in ``sibling(name)``. Liefert stdout (Kurzreport).

    ``--ff-only`` vermeidet Merge-Commits — das Repo bleibt ein reines
    Abbild des Remotes. Gibt es lokale Commits, scheitert pull sauber
    (Aufrufer sieht dirty-Status über :func:`status`).
    """
    if not paths.exists(name):
        raise FileNotFoundError(f"Repo nicht installiert: {name}")
    proc = _run(
        ["pull", "--ff-only"], paths.sibling(name), timeout=_TIMEOUT_NET
    )
    if not _git_ok(proc):
        raise RuntimeError(
            f"pull fehlgeschlagen für {name}: {proc.stderr or proc.stdout or 'unbekannt'}"
        )
    return proc.stdout.strip()


def current_branch(name: str) -> str | None:
    """Aktueller Branch (abgekürzt) oder ``None`` (nicht installiert / detached)."""
    st = status(name)
    if not st.installed:
        return None
    return st.branch
