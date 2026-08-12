"""Subprocess-Management für Long-Running-Prozesse (Server, Barcode-Scanner).

Der ``SubprocessManager`` startet einen Prozess und streamt stdout+stderr
**zeilenweise** über eine thread-safe ``queue.Queue`` — die GUI pollt diese
via ``after()`` und blockiert damit nie den Tkinter-Mainloop.

``stop()`` terminat sauber:
- **Windows**: ``taskkill /T /PID`` beendet den ganzen Prozess-Baum (nötig,
  weil ``uv run`` ein Kind-Python startet — ``terminate()`` auf das Eltern-
  Prozess käme dem Kind nicht bei).
- **POSIX**: ``terminate()`` (SIGTERM); ``uv`` leitet das Signal an das
  Kind weiter. Prozess wird in einer neuen Session gestartet
  (``start_new_session=True``), damit ein group-kill möglich bleibt.

tkinter-frei: Queue + Thread sind reines Python; die GUI bindet sich nur an
``poll_lines()``. Voll testbar auf dem headless VPS (echter Subprocess, kein
Netzwerk).
"""

from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

# Signale, dass der Stream zu Ende ist (Prozess beendet). Einzigartiger
# Sentinel, der nie mit einer echten Log-Zeile kollidiert.
_STREAM_END = object()


class SubprocessManager:
    """Startet/stoppt einen Long-Running-Prozess; streamt sein Log.

    Ein Manager pro Prozess (Server; Barcode nutzt zwei). Zustand nach
    ``stop()`` ist bereit für einen erneuten ``start()``.
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._log: queue.Queue[str | object] = queue.Queue()
        self._return_code: int | None = None

    # --- Start -------------------------------------------------------------

    def start(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Startet ``cmd`` als Subprocess; vorheriger Lauf muss beendet sein.

        ``env`` ersetzt die Prozess-Umgebung komplett (nicht merge) —
        das ist Absicht: so werden IServ-Passwörter via Umgebung gereicht,
        ohne im Kommando (CLI-Args) aufzutauchen (Produktionsschutz). Die
        GUI übergibt ``os.environ.copy() | {…}``.
        """
        if self.is_running():
            raise RuntimeError("Prozess läuft bereits — erst stop() aufrufen")

        # Reset für einen sauberen Lauf (Queue + Returncode leeren).
        self._drain_queue()
        self._return_code = None

        kwargs: dict = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,  # line-buffered
        }
        if env is not None:
            kwargs["env"] = env
        # Neue Prozess-Gruppe auf POSIX, damit ein group-kill möglich ist;
        # auf Windows kümmert sich taskkill /T um den Baum.
        if os.name == "posix":
            kwargs["start_new_session"] = True

        self._process = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, **kwargs)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        """Liest stdout zeilenweise in die Queue, bis der Prozess endet."""
        assert self._process is not None
        proc = self._process
        assert proc.stdout is not None
        # ``for line in proc.stdout`` blockiert bis zur nächsten Zeile; am
        # EOF endet der Iterator sauber. Auch stderr landet hier (STDOUT).
        for line in proc.stdout:
            # Newline am Ende abstreifen; LogView setzt sie beim Anzeigen.
            self._log.put(line.rstrip("\n"))
        proc.wait()
        self._return_code = proc.returncode
        self._log.put(_STREAM_END)
        self._log.put(f"[Prozess beendet — Exit-Code {proc.returncode}]")

    # --- Stop / Status -----------------------------------------------------

    def is_running(self) -> bool:
        """``True`` gdw. der Prozess läuft (``poll() is None``)."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def return_code(self) -> int | None:
        """Exit-Code, falls der Prozess schon beendet ist; sonst ``None``."""
        return self._return_code

    def stop(self, timeout: float = 5.0) -> int | None:
        """Terminat den Prozess sauber. Liefert den Exit-Code oder ``None``.

        Reihenfolge: Prozess-Baum killen (Windows taskkill /T, POSIX
        terminate auf die Gruppe), dann ``wait(timeout)``. Hängt der Prozess,
        wird nach ``timeout`` ein ``kill()`` nachgeschoben.
        """
        proc = self._process
        if proc is None or proc.poll() is not None:
            # Schon beendet — nichts zu tun.
            return self._return_code

        if os.name == "nt":
            # Windows: taskkill /T beendet den ganzen Baum (uv → python).
            subprocess.run(
                ["taskkill", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        else:
            # POSIX: SIGTERM an die neue Prozess-Gruppe, die wir beim Start
            # angelegt haben (start_new_session=True → PGID == PID).
            try:
                os.killpg(os.getpgid(proc.pid), 15)  # SIGTERM
            except (ProcessLookupError, PermissionError):
                proc.terminate()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL
                except (ProcessLookupError, PermissionError):
                    proc.kill()
            proc.wait(timeout=timeout)

        # Thread laufen lassen, bis _STREAM_END ankommt (kurz).
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._return_code = proc.returncode
        return self._return_code

    # --- Log-Stream --------------------------------------------------------

    def poll_lines(self) -> list[str]:
        """Nicht-blockierend: alle gepufferten Log-Zeilen (kann leer sein).

        Stoppt am ``_STREAM_END``-Sentinel. Für die GUI (after()-Polling).
        """
        lines: list[str] = []
        while True:
            try:
                item = self._log.get_nowait()
            except queue.Empty:
                break
            if item is _STREAM_END:
                # Stream zu Ende — weitere Einträge (Beendet-Meldung) holen.
                continue
            lines.append(item)  # type: ignore[arg-type]
        return lines

    def wait_line(self, timeout: float = 1.0) -> str | None:
        """Blockiert bis zu ``timeout`` s auf die nächste Zeile (für Tests)."""
        try:
            item = self._log.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _STREAM_END:
            return None
        return item  # type: ignore[return-value]

    def wait_for_exit(self, timeout: float = 10.0) -> int | None:
        """Wartet auf Prozess-Ende (für Tests); liefert Exit-Code."""
        if self._process is None:
            return self._return_code
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._process.wait(timeout=timeout)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        return self._return_code

    def _drain_queue(self) -> None:
        """Leert die Queue (vor einem neuen Start)."""
        while True:
            try:
                self._log.get_nowait()
            except queue.Empty:
                break


# --- Ein-Schuss-Kommandos (streaming) -------------------------------------
#
# Für Install/Update-Schritte (uv sync, npm install, git pull), die laufen,
# ein Ergebnis liefern und enden — im Gegensatz zum Long-Running-Server,
# der einen SubprocessManager belegt. stdout+stderr werden zeilenweise an
# eine ``log``-Callback gereicht; die GUI hängt sie thread-safe ins LogView.


def run_streaming(
    cmd: list[str] | str,
    log: Callable[[str], None],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 600.0,
    shell: bool = False,
) -> int:
    """Führt ein Ein-Schuss-Kommando aus; streamt stdout+stderr nach ``log``.

    Liefert den Exit-Code. Kein ``raise`` — der Aufrufer prüft auf ``!= 0``
    und erzeugt eine klare Fehlermeldung (mit Kommando + Exit-Code).

    ``shell=True`` (mit ``cmd`` als String) wird für Windows-``.cmd``-Aufrufe
    gebraucht (z. B. ``npm.cmd``); auf POSIX läuft ``npm`` als normales Skript
    und braucht kein Shell.
    """
    log(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
        "shell": shell,
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
