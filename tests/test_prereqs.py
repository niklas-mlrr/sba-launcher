"""Tests für die Node-Helfer in ``core.prereqs`` (Phase 2).

Der echte Download (Windows-zip) ist gemockt; getestet wird die Erkennungs- und
Auflösungslogik: System-node vs. portables Node, PATH-Aufbau, ensure_node-
Reihenfolge und der Windows-only-Schutz des Downloads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import paths, prereqs


@pytest.fixture
def tmp_tools(tmp_path: Path, monkeypatch) -> Path:
    """Biegt ``paths.tools_dir`` auf ein tmp-Verzeichnis."""
    tools = tmp_path / "tools"
    monkeypatch.setattr(paths, "tools_dir", lambda: tools)
    return tools


# --- portable_node_dir / portable_node_exe --------------------------------


def test_portable_node_dir_enthält_version(tmp_tools: Path) -> None:
    pdir = prereqs.portable_node_dir()
    assert pdir.parent == tmp_tools
    assert prereqs.NODE_VERSION in pdir.name


def test_portable_node_exe_none_wenn_fehlt(tmp_tools: Path) -> None:
    assert prereqs.portable_node_exe() is None


def test_portable_node_exe_pfad_wenn_da(tmp_tools: Path) -> None:
    pdir = prereqs.portable_node_dir()
    pdir.mkdir(parents=True)
    (pdir / "node.exe").write_text("fake")
    assert prereqs.portable_node_exe() == pdir / "node.exe"


# --- check_node (mit portabel) --------------------------------------------


def test_check_node_erkennt_portabel(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    pdir = prereqs.portable_node_dir()
    pdir.mkdir(parents=True)
    (pdir / "node.exe").write_text("fake")
    st = prereqs.check_node()
    assert st.available
    assert st.source.startswith("tools/")


def test_check_node_fehlt_wenn_keins(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    st = prereqs.check_node()
    assert not st.available


# --- node_env -------------------------------------------------------------


def test_node_env_ohne_system_node_prependet_portabel(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    pdir = prereqs.portable_node_dir()
    pdir.mkdir(parents=True)
    (pdir / "node.exe").write_text("fake")
    env = prereqs.node_env({"PATH": "/usr/bin"})
    assert env["PATH"].startswith(str(pdir))
    assert "/usr/bin" in env["PATH"]


def test_node_env_mit_system_node_lässt_pathunangetastet(tmp_tools: Path, monkeypatch) -> None:
    # System-node da → portables Node wird NICHT vorgezogen (kein altes portable).
    monkeypatch.setattr(prereqs, "_which", lambda name: "/usr/bin/node" if name == "node" else None)
    pdir = prereqs.portable_node_dir()
    pdir.mkdir(parents=True)
    (pdir / "node.exe").write_text("fake")
    env = prereqs.node_env({"PATH": "/usr/bin"})
    assert env["PATH"] == "/usr/bin"


def test_node_env_ohne_node_und_ohne_portabel(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    env = prereqs.node_env({"PATH": "/usr/bin"})
    assert env["PATH"] == "/usr/bin"


# --- ensure_node ----------------------------------------------------------


def test_ensure_node_system_node_ohne_download(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda name: "/usr/bin/node" if name == "node" else None)
    called = []
    monkeypatch.setattr(prereqs, "_download_portable_node", lambda log: called.append(True))
    assert "im PATH" in prereqs.ensure_node(lambda _m: None)
    assert called == []  # kein Download


def test_ensure_node_portabel_vorhanden_ohne_download(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    pdir = prereqs.portable_node_dir()
    pdir.mkdir(parents=True)
    (pdir / "node.exe").write_text("fake")
    called = []
    monkeypatch.setattr(prereqs, "_download_portable_node", lambda log: called.append(True))
    msg = prereqs.ensure_node(lambda _m: None)
    assert "portables Node gefunden" in msg
    assert called == []


def test_ensure_node_lädt_herunter_wenn_nichts_da(tmp_tools: Path, monkeypatch) -> None:
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)

    def fake_download(log) -> None:
        pdir = prereqs.portable_node_dir()
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "node.exe").write_text("fake")

    monkeypatch.setattr(prereqs, "_download_portable_node", fake_download)
    msg = prereqs.ensure_node(lambda _m: None)
    assert "portables Node installiert" in msg


def test_ensure_node_hebt_auf_posix_ohne_node(tmp_tools: Path, monkeypatch) -> None:
    # Auf dem POSIX-VPS greift der Windows-Guard im realen Download — kein
    # os.name-Patch nötig (und so vermieden wir ein Patchen des globalen os).
    monkeypatch.setattr(prereqs, "_which", lambda _name: None)
    with pytest.raises(RuntimeError, match="nur unter Windows"):
        prereqs.ensure_node(lambda _m: None)


# --- _download_portable_node (Windows-Guard) -----------------------------


def test_download_portable_node_hebt_auf_posix(tmp_tools: Path) -> None:
    with pytest.raises(RuntimeError, match="nur unter Windows"):
        prereqs._download_portable_node(lambda _m: None)


# --- Konstanten -----------------------------------------------------------


def test_node_konstanten_konsistent() -> None:
    assert prereqs.NODE_VERSION.startswith("v")
    assert prereqs.NODE_DOWNLOAD_URL.startswith("https://nodejs.org/dist/")
    assert prereqs.NODE_DOWNLOAD_URL.endswith(".zip")
    assert prereqs.NODE_VERSION in prereqs.NODE_DOWNLOAD_URL
