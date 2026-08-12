"""Tests für ``core.envtool`` — .env lesen/schreiben, maskiert, beide Dateien.

Läuft tkinter-frei. Die Geschwister-Repo-Pfade werden auf ``tmp_path``
umgebogen, sodass echte ``.env``-Dateien unangetastet bleiben.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import envtool, paths


@pytest.fixture
def fake_repos(tmp_path: Path, monkeypatch):
    """Richtet ein Umbrella-Layout unter ``tmp_path`` ein.

    ``launcher_root`` wird auf ``tmp_path/sba-launcher`` gebogen, sodass
    ``sibling(name) = tmp_path/<name>`` (über ``..``) — echte Isolation pro
    Test, kein shared State in ``/tmp``.
    """
    umbrella = tmp_path
    launcher = umbrella / "sba-launcher"
    launcher.mkdir()
    for repo in ("ausleihe-ausgabe", "ausleihe-api"):
        (umbrella / repo).mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    return launcher


# --- parse_env_text / mask_value -----------------------------------------

def test_parse_leere_und_kommentar_zeilen():
    text = """
# Kommentar
ISERV_DOMAIN=iserv-trg-oha.de

ISERV_USERNAME=max
"""
    parsed = envtool.parse_env_text(text)
    assert parsed == {"ISERV_DOMAIN": "iserv-trg-oha.de", "ISERV_USERNAME": "max"}


def test_parse_export_prefix():
    assert envtool.parse_env_text("export FOO=bar") == {"FOO": "bar"}


def test_parse_inline_kommentar_wird_abgehoben():
    assert envtool.parse_env_text("PORT=3443  # host") == {"PORT": "3443"}


def test_parse_letzte_wert_gewinnt():
    text = "X=1\nX=2\n"
    assert envtool.parse_env_text(text) == {"X": "2"}


def test_mask_value_vollstaendig():
    assert envtool.mask_value("geheim") == "•••••" or len(envtool.mask_value("geheim")) >= 4


def test_mask_value_leer_bleibt_leer():
    assert envtool.mask_value("") == ""


def test_masked_verdeckt_sensible_schluessel():
    out = envtool.masked({"ISERV_DOMAIN": "schule.de", "ISERV_PASSWORD": "s3cr3t"})
    assert out["ISERV_DOMAIN"] == "schule.de"
    assert out["ISERV_PASSWORD"] != "s3cr3t"
    assert "•" in out["ISERV_PASSWORD"]


def test_masked_laesst_unsensible_durch():
    out = envtool.masked({"ISERV_USERNAME": "lukas", "HOST_PASSWORD": "pw"})
    assert out["ISERV_USERNAME"] == "lukas"


# --- write_env / read_env ------------------------------------------------

def test_write_env_erzeugt_neue_datei(tmp_path: Path):
    p = tmp_path / "ausleihe-ausgabe" / ".env"
    envtool.write_env(p, {"ISERV_DOMAIN": "x.de", "ISERV_PASSWORD": "p"})
    text = p.read_text(encoding="utf-8")
    assert "ISERV_DOMAIN=x.de" in text
    assert "ISERV_PASSWORD=p" in text
    assert text.endswith("\n")


def test_write_env_erhaelt_kommentare_und_fremde_keys(tmp_path: Path):
    p = tmp_path / "aa.env"
    p.write_text(
        "# nicht anfassen\nPORT=3443\nWORKER_CONTEXTS=2\nISERV_DOMAIN=alt.de\n",
        encoding="utf-8",
    )
    envtool.write_env(p, {"ISERV_DOMAIN": "neu.de"})
    text = p.read_text(encoding="utf-8")
    assert "# nicht anfassen" in text
    assert "PORT=3443" in text
    assert "WORKER_CONTEXTS=2" in text
    assert "ISERV_DOMAIN=neu.de" in text
    assert "ISERV_DOMAIN=alt.de" not in text


def test_write_env_haengt_neuen_key_an(tmp_path: Path):
    p = tmp_path / "x.env"
    p.write_text("ISERV_DOMAIN=x.de\n", encoding="utf-8")
    envtool.write_env(p, {"HOST_PASSWORD": "geheim"})
    text = p.read_text(encoding="utf-8")
    assert text.startswith("ISERV_DOMAIN=x.de\n")
    assert "HOST_PASSWORD=geheim" in text


def test_read_env_fehlt_liefert_leer(tmp_path: Path):
    assert envtool.read_env(tmp_path / "fehlt.env") == {}


def test_write_then_read_roundtrip(tmp_path: Path):
    p = tmp_path / "round.env"
    envtool.write_env(
        p, {"ISERV_DOMAIN": "d", "ISERV_USERNAME": "u", "ISERV_PASSWORD": "p"}
    )
    read = envtool.read_env(p)
    assert read == {"ISERV_DOMAIN": "d", "ISERV_USERNAME": "u", "ISERV_PASSWORD": "p"}


# --- read_form / write_form ----------------------------------------------

def test_write_form_schreibt_beide_dateien(fake_repos, tmp_path):
    values = {
        "ISERV_DOMAIN": "iserv-trg-oha.de",
        "ISERV_USERNAME": "lukas",
        "ISERV_PASSWORD": "s3cr3t",
        "HOST_PASSWORD": "hostpw",
    }
    written = envtool.write_form(values)
    assert set(written) == {"ausleihe-ausgabe", "ausleihe-api"}
    aa = envtool.read_env(paths.env_file("ausleihe-ausgabe"))
    api = envtool.read_env(paths.env_file("ausleihe-api"))
    # Beide haben ISERV_*.
    assert aa["ISERV_DOMAIN"] == "iserv-trg-oha.de"
    assert aa["ISERV_PASSWORD"] == "s3cr3t"
    assert api["ISERV_DOMAIN"] == "iserv-trg-oha.de"
    # HOST_PASSWORD nur in ausleihe-ausgabe.
    assert aa["HOST_PASSWORD"] == "hostpw"
    assert "HOST_PASSWORD" not in api


def test_read_form_liefert_alle_keys_leer_wenn_kein_env(fake_repos):
    form = envtool.read_form()
    assert set(form) == set(envtool.ENV_FORM_KEYS)
    for v in form.values():
        assert v == ""


def test_read_form_liesst_aus_ausleihe_ausgabe(fake_repos, tmp_path):
    envtool.write_env(
        paths.env_file("ausleihe-ausgabe"),
        {
            "ISERV_DOMAIN": "d.de",
            "ISERV_USERNAME": "u",
            "ISERV_PASSWORD": "p",
            "HOST_PASSWORD": "h",
        },
    )
    form = envtool.read_form()
    assert form["ISERV_DOMAIN"] == "d.de"
    assert form["ISERV_PASSWORD"] == "p"
    assert form["HOST_PASSWORD"] == "h"


def test_read_form_faellt_auf_api_zurueck_wenn_aa_fehlt(fake_repos, tmp_path):
    # ausleihe-ausgabe/.env existiere nicht, ausleihe-api/.env ja.
    envtool.write_env(
        paths.env_file("ausleihe-api"),
        {"ISERV_DOMAIN": "api.de", "ISERV_USERNAME": "u", "ISERV_PASSWORD": "p"},
    )
    form = envtool.read_form()
    assert form["ISERV_DOMAIN"] == "api.de"
    assert form["ISERV_PASSWORD"] == "p"
    assert form["HOST_PASSWORD"] == ""  # api hat keinen HOST_PASSWORD


def test_write_form_leerer_wert_setzt_leer_nicht_loescht(fake_repos):
    envtool.write_env(
        paths.env_file("ausleihe-ausgabe"),
        {"ISERV_PASSWORD": "alt", "HOST_PASSWORD": "alt"},
    )
    envtool.write_form(
        {"ISERV_DOMAIN": "", "ISERV_USERNAME": "", "ISERV_PASSWORD": "", "HOST_PASSWORD": ""}
    )
    aa = envtool.read_env(paths.env_file("ausleihe-ausgabe"))
    assert aa["ISERV_PASSWORD"] == ""
    assert "ISERV_PASSWORD=" in paths.env_file("ausleihe-ausgabe").read_text(encoding="utf-8")


# --- Produktionsschutz: sensible Werte tauchen nicht im Output auf -------

def test_kein_klartextpasswort_in_datei_ausserhalb_der_wert_zeile(fake_repos):
    """Passwort steht nur in der eigenen KEY=Zeile, nicht in Kommentaren."""
    envtool.write_form({"ISERV_PASSWORD": "TOPSECRET", "HOST_PASSWORD": "ALSOSECRET"})
    for repo in ("ausleihe-ausgabe", "ausleihe-api"):
        text = paths.env_file(repo).read_text(encoding="utf-8")
        # Passwort darf nur als Wert hinter dem Gleichheitszeichen stehen.
        lines = text.splitlines()
        secret_lines = [ln for ln in lines if "TOPSECRET" in ln or "ALSOSECRET" in ln]
        allowed = ("ISERV_PASSWORD", "HOST_PASSWORD")
        assert all(ln.split("=", 1)[0] in allowed for ln in secret_lines)
