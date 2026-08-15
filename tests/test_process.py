"""Tests für ``core.process.SubprocessManager`` — start/stop/log.

Läuft tkinter-frei auf dem headless VPS. Verwendet ``sys.executable -u``
(unbuffered), damit ``print``-Zeilen sofort im Stream ankommen (Python
block-buffered stdout, wenn es in eine Pipe schreibt).
"""

from __future__ import annotations

import sys
import time

import pytest

from core.process import SubprocessManager, run_streaming

_PY = [sys.executable, "-u"]


def _wait_for_line(m: SubprocessManager, want: str, timeout: float = 5.0) -> bool:
    """Sammelt Zeilen bis ``want`` auftaucht oder ``timeout`` abläuft."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for ln in m.poll_lines():
            if want in ln:
                return True
        time.sleep(0.02)
    return False


# --- start / stop ---------------------------------------------------------

def test_start_dann_stop_beendet_prozess() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "import time\nprint('a')\ntime.sleep(30)"])
    try:
        assert m.is_running()
        assert _wait_for_line(m, "a")
    finally:
        code = m.stop(timeout=5)
    assert code is not None
    assert not m.is_running()


def test_stop_ohne_laufenden_prozess_liefert_none() -> None:
    m = SubprocessManager()
    assert m.stop() is None
    assert not m.is_running()


def test_stop_nach_natuerlichem_exit_liefert_echten_returncode() -> None:
    """Wave 1: stop() nach eigenständigem Prozessende liefert rc, nicht None."""
    m = SubprocessManager()
    m.start([*_PY, "-c", "import sys; sys.exit(7)"])
    deadline = time.monotonic() + 5.0
    while m._process.poll() is None and time.monotonic() < deadline:  # noqa: SLF001
        time.sleep(0.02)
    assert m._process.poll() is not None  # noqa: SLF001
    assert m.stop() == 7


def test_doppel_start_hebt() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(RuntimeError):
            m.start([*_PY, "-c", "print('x')"])
    finally:
        m.stop()


# --- Log-Stream / Exit-Codes ----------------------------------------------

def test_stream_liefert_zeilen_in_reihenfolge() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "print('eins')\nprint('zwei')"])
    code = m.wait_for_exit(timeout=5)
    assert code == 0
    lines = m.poll_lines()
    assert "eins" in lines
    assert "zwei" in lines
    assert lines.index("eins") < lines.index("zwei")


def test_exit_code_nonzero() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "import sys; print('boom'); sys.exit(3)"])
    code = m.wait_for_exit(timeout=5)
    assert code == 3


def test_beendet_markiert_prozess_ende() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "print('fertig')"])
    m.wait_for_exit(timeout=5)
    lines = m.poll_lines()
    assert any("Prozess beendet" in ln for ln in lines)
    assert "Exit-Code 0" in "".join(lines)


def test_poll_lines_leer_ohne_output() -> None:
    m = SubprocessManager()
    assert m.poll_lines() == []


# --- erneuter Start nach Stop -------------------------------------------

def test_neustart_nach_stop() -> None:
    m = SubprocessManager()
    m.start([*_PY, "-c", "print('erst')"])
    m.wait_for_exit(timeout=5)
    m.poll_lines()  # verwerfen

    # Zweiter Lauf: Queue muss zurückgesetzt sein (kein 'erst' mehr drin).
    m.start([*_PY, "-c", "print('zweit')"])
    code = m.wait_for_exit(timeout=5)
    assert code == 0
    lines = m.poll_lines()
    assert "zweit" in lines
    assert "erst" not in lines


# --- run_streaming (Ein-Schuss-Kommando) -----------------------------------


def test_run_streaming_liefert_zeilen_und_rc_0() -> None:
    """Realer Subprocess: print('hi') → rc 0, Output enthält 'hi', Echo ``$ …``."""
    logs: list[str] = []
    rc = run_streaming([*_PY, "-u", "-c", "print('hi')"], log=logs.append)
    assert rc == 0
    assert any(ln.startswith("$ ") for ln in logs)
    assert "hi" in " ".join(logs)


def test_run_streaming_timeout_killt_prozess() -> None:
    """Timeout killt den Prozess und liefert nonzero rc."""
    logs: list[str] = []
    rc = run_streaming(
        [*_PY, "-u", "-c", "import time; time.sleep(30)"],
        log=logs.append,
        timeout=0.5,
    )
    assert rc != 0
    assert any("Zeitüberschreitung" in ln for ln in logs)
