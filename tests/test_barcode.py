"""Tests für ``core.barcode`` — Pfad-Helfer, session.json, Scanner-URL, start/stop.

tkinter-frei und ohne echtes Node/pyautogui: ``start``/``stop`` laufen gegen
Fake-SubprocessManager, die ``node``-Auflösung und das session.json-Warten
sind gemockt. Install/Update (clone+npm+venv) greifen ins Netz/Dateisystem
und sind hier nicht abgedeckt — analog zu ``test_ausleihe``.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from core import barcode as bc
from core import paths


@pytest.fixture
def fake_barcode_repo(tmp_path: Path, monkeypatch) -> Path:
    """Biegt ``barcode-simple`` auf ein tmp-Repo (mit .git + runtime-Dir)."""
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    repo = tmp_path / "barcode-simple"
    (repo / ".git").mkdir(parents=True)
    (repo / "server" / "runtime").mkdir(parents=True)
    return repo


class FakeManager:
    """SubprocessManager-Stub: zeichnet start/stop auf, ohne echte Prozesse."""

    def __init__(self) -> None:
        self.started: list[tuple[list[str], Path | None, dict | None]] = []
        self.running = False
        self.stopped = False
        self.stop_calls = 0

    def start(self, cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
        self.started.append((cmd, cwd, env))
        self.running = True

    def is_running(self) -> bool:
        return self.running

    def stop(self, timeout: float = 5.0) -> int:
        self.stop_calls += 1
        self.running = False
        self.stopped = True
        return 0

    def poll_lines(self) -> list[str]:
        return []


# --- parse_scanner_url ----------------------------------------------------


def test_parse_scanner_url_findet_url() -> None:
    line = "Scanner URL: https://192.168.1.42:3443/#s=abcdef0123456789"
    assert bc.parse_scanner_url(line) == "https://192.168.1.42:3443/#s=abcdef0123456789"


def test_parse_scanner_url_liefert_none_für_andere_zeilen() -> None:
    assert bc.parse_scanner_url("Barcode server running at https://1.2.3.4:3443") is None
    assert bc.parse_scanner_url("  ▀▀▀▀▀  (ASCII-QR-Art)") is None
    assert bc.parse_scanner_url("") is None


def test_parse_scanner_url_search_nicht_anchored() -> None:
    # Zeile kann führenden Whitespace/Prefix tragen — search findet sie trotzdem.
    assert bc.parse_scanner_url("  [server] Scanner URL: https://10.0.0.7:3443/#s=xyz") == (
        "https://10.0.0.7:3443/#s=xyz"
    )


# --- read_session ---------------------------------------------------------


def test_read_session_liefert_none_wenn_fehlt(fake_barcode_repo: Path) -> None:
    assert bc.read_session() is None


def test_read_session_liest_gültige_datei(fake_barcode_repo: Path) -> None:
    sf = bc.session_file()
    sf.write_text(
        json.dumps({"v": 2, "port": 3443, "certPath": "/x/cert.pem", "desktopToken": "t" * 64}),
        encoding="utf8",
    )
    data = bc.read_session()
    assert data is not None
    assert data["port"] == 3443
    assert data["desktopToken"] == "t" * 64


def test_read_session_liefert_none_bei_kaputtem_json(fake_barcode_repo: Path) -> None:
    bc.session_file().write_text("{kein json", encoding="utf8")
    assert bc.read_session() is None


# --- Pfad-Helfer ----------------------------------------------------------


def test_session_file_pfad(fake_barcode_repo: Path) -> None:
    assert bc.session_file().resolve() == (
        fake_barcode_repo / "server" / "runtime" / "session.json"
    ).resolve()


def test_server_dir(fake_barcode_repo: Path) -> None:
    assert bc.server_dir().resolve() == (fake_barcode_repo / "server").resolve()


def test_venv_python_rel_windows() -> None:
    assert bc.venv_python_rel("nt") == Path("Scripts") / "python.exe"


def test_venv_python_rel_posix() -> None:
    assert bc.venv_python_rel("posix") == Path("bin") / "python"


def test_client_venv_python_baut_aus_venv_rel(fake_barcode_repo: Path) -> None:
    # posix (VPS) → bin/python; nur Struktur prüfen (kein os-Patch nötig).
    p = bc.client_venv_python()
    assert p.parts[-2:] == ("bin", "python")
    assert ".venv-client" in p.parts


# --- _wait_for_session ----------------------------------------------------


def test_wait_for_session_true_wenn_datei_erscheint(fake_barcode_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(bc, "SESSION_TIMEOUT_S", 2.0)
    monkeypatch.setattr(bc, "SESSION_POLL_INTERVAL_S", 0.02)
    sf = bc.session_file()

    def create_soon() -> None:
        time.sleep(0.1)
        sf.write_text("{}", encoding="utf8")

    threading.Thread(target=create_soon, daemon=True).start()
    assert bc._wait_for_session(sf, lambda _l: None) is True


def test_wait_for_session_false_bei_timeout(fake_barcode_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(bc, "SESSION_TIMEOUT_S", 0.1)
    monkeypatch.setattr(bc, "SESSION_POLL_INTERVAL_S", 0.02)
    assert bc._wait_for_session(bc.session_file(), lambda _l: None) is False


# --- start ----------------------------------------------------------------


def _patch_start_voraussetzungen(fake_barcode_repo: Path, monkeypatch) -> Path:
    """Stellt vorgetäuschte Node- + Venv-Voraussetzungen für start() her."""
    monkeypatch.setattr(bc.prereqs, "node_bin", lambda: sys.executable)
    venv_py = bc.client_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake venv python", encoding="utf8")
    return venv_py


def test_start_startet_server_dann_client(fake_barcode_repo: Path, monkeypatch) -> None:
    venv_py = _patch_start_voraussetzungen(fake_barcode_repo, monkeypatch)
    monkeypatch.setattr(bc, "_wait_for_session", lambda sf, log: True)
    server, client = FakeManager(), FakeManager()
    logs: list[str] = []

    bc.start(server, client, logs.append)

    # Server zuerst, Client danach.
    assert len(server.started) == 1
    assert len(client.started) == 1
    server_cmd, server_cwd, _ = server.started[0]
    assert server_cmd[0] == sys.executable  # node_bin gemockt
    assert server_cmd[1] == "server/server.js"
    assert server_cwd.resolve() == fake_barcode_repo.resolve()
    client_cmd, _, _ = client.started[0]
    assert client_cmd[0] == str(venv_py)
    assert client_cmd[1] == "client/client.py"
    assert "--session-file" in client_cmd
    # --session-file bekommt den absoluten Pfad.
    sf_idx = client_cmd.index("--session-file")
    assert client_cmd[sf_idx + 1] == str(bc.session_file())


def test_start_löscht_alte_session_json(fake_barcode_repo: Path, monkeypatch) -> None:
    _patch_start_voraussetzungen(fake_barcode_repo, monkeypatch)
    sf = bc.session_file()
    sf.write_text("stale", encoding="utf8")
    monkeypatch.setattr(bc, "_wait_for_session", lambda s, log: True)

    bc.start(FakeManager(), FakeManager(), lambda _l: None)
    # _wait_for_session gemockt (True) → Datei bleibt gelöscht (nicht recreated).
    assert not sf.exists()


def test_start_hebt_wenn_repo_fehlt(tmp_path: Path, monkeypatch) -> None:
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    with pytest.raises(FileNotFoundError, match="nicht installiert"):
        bc.start(FakeManager(), FakeManager(), lambda _l: None)


def test_start_hebt_wenn_venv_fehlt(fake_barcode_repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(bc.prereqs, "node_bin", lambda: sys.executable)
    # Kein Venv angelegt → client_venv_python().is_file() ist False.
    with pytest.raises(FileNotFoundError, match="Client-Venv fehlt"):
        bc.start(FakeManager(), FakeManager(), lambda _l: None)


def test_start_hebt_wenn_node_fehlt(fake_barcode_repo: Path, monkeypatch) -> None:
    _patch_start_voraussetzungen(fake_barcode_repo, monkeypatch)
    monkeypatch.setattr(bc.prereqs, "node_bin", lambda: "")
    with pytest.raises(FileNotFoundError, match="Node.js fehlt"):
        bc.start(FakeManager(), FakeManager(), lambda _l: None)


def test_start_stoppt_server_wenn_session_timeout(fake_barcode_repo: Path, monkeypatch) -> None:
    _patch_start_voraussetzungen(fake_barcode_repo, monkeypatch)
    monkeypatch.setattr(bc, "_wait_for_session", lambda sf, log: False)
    server, client = FakeManager(), FakeManager()
    with pytest.raises(RuntimeError, match="session.json"):
        bc.start(server, client, lambda _l: None)
    # Server wurde gestartet, dann (nach Timeout) wieder gestoppt.
    assert len(server.started) == 1
    assert server.stop_calls == 1
    # Client wurde NICHT gestartet (session.json fehlte).
    assert len(client.started) == 0


# --- stop -----------------------------------------------------------------


def test_stop_beendet_beide_und_räumt_session(fake_barcode_repo: Path) -> None:
    sf = bc.session_file()
    sf.write_text("{}", encoding="utf8")
    server, client = FakeManager(), FakeManager()
    server.running = True
    client.running = True

    codes = bc.stop(server, client, lambda _l: None)

    assert client.stopped and server.stopped
    assert codes == {"client": 0, "server": 0}
    assert not sf.exists()


def test_stop_client_zuerst_dann_server(fake_barcode_repo: Path) -> None:
    """Client wird vor dem Server gestoppt (Reihenfolge in stop())."""
    order: list[str] = []

    class OrderedFake(FakeManager):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

        def stop(self, timeout: float = 5.0) -> int:
            order.append(self.name)
            return super().stop(timeout)

    client, server = OrderedFake("client"), OrderedFake("server")
    bc.stop(server, client, lambda _l: None)
    assert order == ["client", "server"]


# --- Konstanten -----------------------------------------------------------


def test_konstanten_konsistent() -> None:
    assert bc.SERVER_PORT_DEFAULT == 3443
    assert Path("server/server.js") == bc.SERVER_SCRIPT
    assert Path("client/client.py") == bc.CLIENT_SCRIPT
    assert Path("server/runtime/session.json") == bc.SESSION_REL
    assert Path(".venv-client") == bc.CLIENT_VENV_DIR
    assert bc.SESSION_TIMEOUT_S > 0
