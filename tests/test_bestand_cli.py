"""Tests für ``core.bestand`` — Pfad-Helfer, Kommando-Bau, install/update/run_auto.

tkinter-frei und ohne echtes uv/IServ: ``run_auto`` greift auf einen gemockten
``run_streaming`` zu; install/update klonen/syncen und sind (wie test_ausleihe/
test_barcode) nicht abgedeckt — hier nur die Vorbedingungs-Checks + der
Kommando-Bau, der der kritische Teil ist (richtige Flags, absolute Excel).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import bestand as bst
from core import paths
from tests.conftest import make_repo


@pytest.fixture
def fake_bestand_repo(umbrella: Path) -> Path:
    """Biegt den Launcher-Root auf tmp; legt ausleihe-api + Bestand-Dir an."""
    repo = make_repo(umbrella, "ausleihe-api")
    (repo / "bestand- und nachbestellungen" / "New - API approach").mkdir(parents=True)
    return repo


def _seed_skript_venv_env(fake_bestand_repo: Path) -> Path:
    """Stellt die Vorbedingungen für run_auto her: Skript + Venv-Python + .env."""
    skript = bst.script_path()
    skript.write_text("# fake bestand script", encoding="utf-8")
    venv_py = bst.bestand_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake venv python", encoding="utf-8")
    bst.env_file().write_text("ISERV_DOMAIN=trg\n", encoding="utf-8")
    return venv_py


# --- Konstanten / Pfade ---------------------------------------------------


def test_konstanten_konsistent() -> None:
    assert Path("bestand- und nachbestellungen/New - API approach") == bst.BESTAND_DIR_REL
    assert bst.BESTAND_SCRIPT_REL == bst.BESTAND_DIR_REL / "update_bestand_auto.py"
    assert bst.BESTAND_CONFIG_REL == bst.BESTAND_DIR_REL / "config.json"
    assert Path(".venv-bestand") == bst.BESTAND_VENV_DIR
    assert bst.BESTAND_EXTRA == "bestand"


def test_venv_python_rel_windows() -> None:
    assert bst.venv_python_rel("nt") == Path("Scripts") / "python.exe"


def test_venv_python_rel_posix() -> None:
    assert bst.venv_python_rel("posix") == Path("bin") / "python"


def test_script_und_config_pfad(fake_bestand_repo: Path) -> None:
    base = (fake_bestand_repo / "bestand- und nachbestellungen" / "New - API approach").resolve()
    assert bst.script_path().resolve() == (base / "update_bestand_auto.py").resolve()
    assert bst.config_path().resolve() == (base / "config.json").resolve()


def test_bestand_venv_python_baut_aus_venv_rel(fake_bestand_repo: Path) -> None:
    p = bst.bestand_venv_python()
    assert p.parts[-2:] == ("bin", "python")
    assert ".venv-bestand" in p.parts


# --- build_cmd (kritisch: Flags + absolute Excel) -------------------------


def test_build_cmd_dry_run_setzt_flag() -> None:
    cmd = bst.build_cmd(dry_run=True, excel=Path("/tmp/B.xlsx"))
    assert "--dry-run" in cmd
    assert "-v" in cmd


def test_build_cmd_real_ohne_dry_run_flag() -> None:
    cmd = bst.build_cmd(dry_run=False, excel=Path("/tmp/B.xlsx"))
    assert "--dry-run" not in cmd


def test_build_cmd_excel_absolut(tmp_path: Path) -> None:
    excel = tmp_path / "Bestand 2026.xlsx"
    cmd = bst.build_cmd(dry_run=True, excel=excel)
    idx = cmd.index("--excel")
    # resolve() → absoluter Pfad (Skript rechnet _HERE / "<abs>" == "<abs>").
    assert cmd[idx + 1] == str(excel.resolve())


def test_build_cmd_excel_string_wird_absolut(tmp_path: Path) -> None:
    excel = tmp_path / "B.xlsx"
    cmd = bst.build_cmd(dry_run=True, excel=str(excel))
    idx = cmd.index("--excel")
    assert Path(cmd[idx + 1]).is_absolute()


def test_build_cmd_ohne_excel_kein_flag() -> None:
    cmd = bst.build_cmd(dry_run=True, excel=None)
    assert "--excel" not in cmd


def test_build_cmd_schoolyear_wird_durchgereicht() -> None:
    cmd = bst.build_cmd(dry_run=True, excel=Path("/x.xlsx"), schoolyear="2025/2026")
    idx = cmd.index("--schoolyear")
    assert cmd[idx + 1] == "2025/2026"


def test_build_cmd_safety_stock_wird_durchgereicht() -> None:
    cmd = bst.build_cmd(dry_run=True, excel=Path("/x.xlsx"), safety_stock=12)
    idx = cmd.index("--safety-stock")
    assert cmd[idx + 1] == "12"


# --- run_auto (gemockt) ---------------------------------------------------


def test_run_auto_baut_kommando_mit_venv_python(fake_bestand_repo: Path, monkeypatch) -> None:
    venv_py = _seed_skript_venv_env(fake_bestand_repo)
    captured: list[list[str]] = []

    def fake_run(cmd, log=None, cwd=None, env=None, timeout=600.0, shell=False):
        captured.append(cmd)
        return 0

    monkeypatch.setattr(bst, "run_streaming", fake_run)
    rc = bst.run_auto(dry_run=True, excel=Path("/tmp/B.xlsx"), log=lambda _l: None)
    assert rc == 0
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == str(venv_py)
    assert cmd[1] == str(bst.script_path())
    assert "--dry-run" in cmd
    assert "--excel" in cmd


def test_run_auto_real_ohne_dry_run_flag(fake_bestand_repo: Path, monkeypatch) -> None:
    _seed_skript_venv_env(fake_bestand_repo)
    captured: list[list[str]] = []

    def fake_run(cmd, log=None, cwd=None, env=None, timeout=600.0, shell=False):
        captured.append(cmd)
        return 0

    monkeypatch.setattr(bst, "run_streaming", fake_run)
    rc = bst.run_auto(dry_run=False, excel=Path("/x.xlsx"), log=lambda _l: None)
    assert rc == 0
    assert len(captured) == 1
    assert "--dry-run" not in captured[0]


def test_run_auto_streamt_log(fake_bestand_repo: Path, monkeypatch) -> None:
    _seed_skript_venv_env(fake_bestand_repo)

    def fake_run(cmd, log=None, cwd=None, **kw):
        log("Verbinde mit IServ …")
        log("-- DRY RUN: keine Datei wird gespeichert --")
        return 0

    monkeypatch.setattr(bst, "run_streaming", fake_run)
    logs: list[str] = []
    rc = bst.run_auto(dry_run=True, excel=Path("/x.xlsx"), log=logs.append)
    assert rc == 0
    assert "Verbinde mit IServ …" in logs
    assert any("DRY RUN" in ln for ln in logs)
    assert any("Exit-Code 0" in ln for ln in logs)


def test_run_auto_cwd_ist_bestand_dir(fake_bestand_repo: Path, monkeypatch) -> None:
    _seed_skript_venv_env(fake_bestand_repo)
    captured: dict = {}

    def fake_run(cmd, log=None, cwd=None, **kw):
        captured["cwd"] = cwd
        return 0

    monkeypatch.setattr(bst, "run_streaming", fake_run)
    bst.run_auto(dry_run=True, excel=Path("/x.xlsx"), log=lambda _l: None)
    assert captured["cwd"].resolve() == bst.bestand_dir().resolve()


def test_run_auto_liefert_exit_code(fake_bestand_repo: Path, monkeypatch) -> None:
    _seed_skript_venv_env(fake_bestand_repo)
    monkeypatch.setattr(bst, "run_streaming", lambda *a, **k: 2)
    rc = bst.run_auto(dry_run=True, excel=Path("/x.xlsx"), log=lambda _l: None)
    assert rc == 2


# --- run_auto Vorbedingungen (heurben) ------------------------------------


def test_run_auto_hebt_wenn_repo_fehlt(tmp_path: Path, monkeypatch) -> None:
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    with pytest.raises(FileNotFoundError, match="nicht installiert"):
        bst.run_auto(dry_run=True, log=lambda _l: None)


def test_run_auto_hebt_wenn_skript_fehlt(fake_bestand_repo: Path, monkeypatch) -> None:
    # Repo da, aber kein Skript.
    venv_py = bst.bestand_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake", encoding="utf-8")
    bst.env_file().write_text("ISERV_DOMAIN=x\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Bestand-Skript fehlt"):
        bst.run_auto(dry_run=True, log=lambda _l: None)


def test_run_auto_hebt_wenn_venv_fehlt(fake_bestand_repo: Path, monkeypatch) -> None:
    bst.script_path().write_text("# fake", encoding="utf-8")
    bst.env_file().write_text("ISERV_DOMAIN=x\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Bestand-Venv fehlt"):
        bst.run_auto(dry_run=True, log=lambda _l: None)


def test_run_auto_hebt_wenn_env_fehlt(fake_bestand_repo: Path, monkeypatch) -> None:
    bst.script_path().write_text("# fake", encoding="utf-8")
    venv_py = bst.bestand_venv_python()
    venv_py.parent.mkdir(parents=True, exist_ok=True)
    venv_py.write_text("# fake", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=r"\.env fehlt"):
        bst.run_auto(dry_run=True, log=lambda _l: None)


# --- install: Kommando als Liste (kein shell=True) -------------------------


def test_install_reicht_kommandos_als_liste(fake_bestand_repo: Path, monkeypatch) -> None:
    """install() reicht run_streaming-Kommandos als Liste (kein shell=True)."""
    captured: list[dict] = []

    def fake_run(cmd, log=None, cwd=None, env=None, timeout=600.0, shell=False):
        captured.append({"cmd": cmd, "shell": shell})
        return 0

    monkeypatch.setattr(bst, "run_streaming", fake_run)
    bst.install(log=lambda _l: None)
    # uv venv + uv pip install.
    assert len(captured) >= 2
    for call in captured:
        assert isinstance(call["cmd"], list)
        assert call["shell"] is False
    pip_calls = [c for c in captured if "pip" in c["cmd"]]
    assert pip_calls
    assert pip_calls[0]["cmd"][0] == "uv"
    assert "install" in pip_calls[0]["cmd"]
    assert "-e" in pip_calls[0]["cmd"]
    assert f".[{bst.BESTAND_EXTRA}]" in pip_calls[0]["cmd"]
