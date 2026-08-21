"""Tests für ``core.config_io`` — Bestand-config.json lesen/schreiben/validieren.

tkinter-frei und ohne IServ-Kontakt: arbeitet gegen eine tmp-config.json.
``bestand.config_path()`` wird über ``paths.launcher_root`` auf tmp gebogen.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import config_io


@pytest.fixture
def fake_bestand_repo(umbrella: Path) -> Path:
    """Biegt den Launcher-Root auf tmp; legt das Bestand-Dir (ohne config) an."""
    # sba-bestand existiert als Verzeichnis (config_path() zeigt dorthin).
    (umbrella / "sba-bestand" / "bestand").mkdir(parents=True)
    return umbrella / "sba-launcher"


def _cfg_path() -> Path:
    return config_io.bestand.config_path()


def _write_cfg(d: dict) -> None:
    p = _cfg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


# --- read_config ----------------------------------------------------------


def test_read_defaults_wenn_datei_fehlt(fake_bestand_repo: Path) -> None:
    cfg = config_io.read_config()
    assert cfg.safety_stock == config_io.DEFAULT_SAFETY_STOCK == 5
    assert cfg.match_overrides == {}
    assert cfg.excel_file is None
    assert cfg.sheet_name is None


def test_read_liefert_alle_felder(fake_bestand_repo: Path) -> None:
    _write_cfg({
        "excel_file": "Bestand 2026.xlsx",
        "sheet_name": "Bestand- und Nachbestellung",
        "safety_stock": 8,
        "match_overrides": {"5|Deutsch|": "9783062052224"},
        "mappings": [{"isbn": "123", "bestand_cell": "C4"}],
    })
    cfg = config_io.read_config()
    assert cfg.excel_file == "Bestand 2026.xlsx"
    assert cfg.sheet_name == "Bestand- und Nachbestellung"
    assert cfg.safety_stock == 8
    assert cfg.match_overrides == {"5|Deutsch|": "9783062052224"}
    assert cfg.mappings == [{"isbn": "123", "bestand_cell": "C4"}]


def test_read_repariert_ungültigen_safety_stock(fake_bestand_repo: Path) -> None:
    _write_cfg({"safety_stock": -3})
    cfg = config_io.read_config()
    assert cfg.safety_stock == config_io.DEFAULT_SAFETY_STOCK


def test_read_repariert_nicht_dict_match_overrides(fake_bestand_repo: Path) -> None:
    _write_cfg({"match_overrides": ["kein", "dict"]})
    cfg = config_io.read_config()
    assert cfg.match_overrides == {}


def test_read_behält_unbekannte_keys_in_raw(fake_bestand_repo: Path) -> None:
    _write_cfg({"safety_stock": 2, "zukunft_key": 42})
    cfg = config_io.read_config()
    assert cfg.raw == {"zukunft_key": 42}


# --- write_editable (Erhalt anderer Keys) ---------------------------------


def test_write_editable_erhält_excel_sheet_mappings(fake_bestand_repo: Path) -> None:
    _write_cfg({
        "excel_file": "B.xlsx",
        "sheet_name": "S",
        "safety_stock": 3,
        "match_overrides": {},
        "mappings": [{"isbn": "x", "bestand_cell": "C4"}],
    })
    config_io.write_editable(10, {"7|Mathe|": "111"})
    data = json.loads(_cfg_path().read_text(encoding="utf-8"))
    assert data["excel_file"] == "B.xlsx"
    assert data["sheet_name"] == "S"
    assert data["safety_stock"] == 10
    assert data["match_overrides"] == {"7|Mathe|": "111"}
    assert data["mappings"] == [{"isbn": "x", "bestand_cell": "C4"}]


def test_write_editable_legt_datei_an_wenn_fehlt(fake_bestand_repo: Path) -> None:
    assert not _cfg_path().exists()
    config_io.write_editable(5, {})
    data = json.loads(_cfg_path().read_text(encoding="utf-8"))
    assert data["safety_stock"] == 5
    assert data["match_overrides"] == {}


def test_write_editable_behält_unbekannte_keys(fake_bestand_repo: Path) -> None:
    _write_cfg({"safety_stock": 1, "zukunft_key": 99})
    config_io.write_editable(2, {})
    data = json.loads(_cfg_path().read_text(encoding="utf-8"))
    assert data["zukunft_key"] == 99


def test_write_config_format_ensure_ascii_false(fake_bestand_repo: Path) -> None:
    config_io.write_editable(1, {"5|Deutsch|": "978"})
    text = _cfg_path().read_text(encoding="utf-8")
    # Keine \uXXXX-Escapes (Umlaute direkt). Schließt indent=2 nicht aus.
    assert "\\u" not in text


# --- Validierung ----------------------------------------------------------


def test_validate_reject_negativen_safety_stock() -> None:
    with pytest.raises(config_io.ConfigError, match="negativ"):
        config_io.validate_editable(-1, {})


def test_validate_reject_bool_als_safety_stock() -> None:
    # bool ist int-Subclass — darf nicht durchgehen.
    with pytest.raises(config_io.ConfigError, match="ganze Zahl"):
        config_io.validate_editable(True, {})  # noqa: FBT003


def test_validate_reject_nicht_int_safety_stock() -> None:
    with pytest.raises(config_io.ConfigError, match="ganze Zahl"):
        config_io.validate_editable("5", {})  # type: ignore[arg-type]


def test_validate_reject_nicht_dict_overrides() -> None:
    with pytest.raises(config_io.ConfigError, match="Objekt"):
        config_io.validate_editable(5, [])  # type: ignore[arg-type]


def test_validate_reject_nicht_string_in_overrides() -> None:
    with pytest.raises(config_io.ConfigError, match="String"):
        config_io.validate_editable(5, {"k": 123})  # type: ignore[dict-item]


def test_validate_accepts_leer_und_null() -> None:
    config_io.validate_editable(0, {})  # kein Raise


# --- parse/format match_overrides -----------------------------------------


def test_parse_leerer_text_liefert_leeres_dict() -> None:
    assert config_io.parse_match_overrides_text("") == {}
    assert config_io.parse_match_overrides_text("   ") == {}


def test_parse_gültiges_json() -> None:
    txt = '{"5|Deutsch|": "9783062052224", "11|Politik|eA": "123"}'
    assert config_io.parse_match_overrides_text(txt) == {
        "5|Deutsch|": "9783062052224",
        "11|Politik|eA": "123",
    }


def test_parse_kaputtes_json_wirft() -> None:
    with pytest.raises(config_io.ConfigError, match="kein gültiges JSON"):
        config_io.parse_match_overrides_text("{kein json")


def test_parse_liste_statt_objekt_wirft() -> None:
    with pytest.raises(config_io.ConfigError, match="Objekt"):
        config_io.parse_match_overrides_text("[1, 2]")


def test_parse_nicht_string_werte_wirft() -> None:
    with pytest.raises(config_io.ConfigError, match="String"):
        config_io.parse_match_overrides_text('{"k": 5}')


def test_format_match_overrides_liefert_json() -> None:
    txt = config_io.format_match_overrides({"b": "2", "a": "1"})
    assert json.loads(txt) == {"a": "1", "b": "2"}  # sort_keys=True


# --- Roundtrip (read ↔ write) ---------------------------------------------


def test_roundtrip_read_write_read(fake_bestand_repo: Path) -> None:
    config_io.write_editable(7, {"5|Deutsch|": "978", "9|Bio|": "456"})
    cfg = config_io.read_config()
    assert cfg.safety_stock == 7
    assert cfg.match_overrides == {"5|Deutsch|": "978", "9|Bio|": "456"}
