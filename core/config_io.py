"""Lesen/Schreiben der Bestand-``config.json`` (Roh-Editor-Basis).

Die ``config.json`` liegt neben ``update_bestand_auto.py`` im ausleihe-api-Repo
(``bestand- und nachbestellungen/New - API approach/config.json``) und enthält:

- ``excel_file`` / ``sheet_name`` — Layout-Bezug (nicht vom Launcher editiert),
- ``safety_stock`` — zusätzlicher Sicherheitsbestand je Titel (MVP-editierbar),
- ``match_overrides`` — ``{"<grade>|<fach>|<hint>": "<isbn>"}`` bei mehrdeutigen
  Treffern (MVP-editierbar als Roh-Editor),
- ``mappings`` — Legacy-Zellen-Mapping des alten Skripts (unangetastet gelassen).

Phase 3 bietet nur einen **Roh-Editor** für ``safety_stock`` + ``match_overrides``
(strings/JSON). Der Voll-Katalog-Editor folgt in Phase 4 (``core.catalog``).

Produktionsschutz (CLAUDE.md): ``config.json`` enthält keine Credentials und wird
nur lokal geschrieben — kein IServ-Kontakt. ``match_overrides``-Werte sind ISBNs,
keine Schülerdaten.

tkinter-frei — auf dem headless VPS via pytest testbar.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from core import bestand

# Default-Sicherheitsbestand, falls die config.json (noch) nicht existiert oder
# keinen Wert angibt — geeint mit update_bestand_auto.py (dort: config.get(…, 5)).
DEFAULT_SAFETY_STOCK = 5


def _atomic_write_text(path: Path, text: str) -> None:
    """Schreibt ``text`` atomar nach ``path`` (Temp-Datei + ``os.replace``).

    Verhindert halbfertige Dateien bei Absturz/Interrupt: erst in eine
    Temporärdatei ``path.suffix + ".tmp"`` im **selben Verzeichnis** schreiben
    (gleiche Partition → ``os.replace`` ist atomar), dann umbenennen. Die
    Temp-Datei wird direkt mit ``0o600`` (nur Owner) angelegt — nicht erst per
    ``chmod`` danach —, damit sie bei einem Crash zwischen Schreiben und
    ``os.replace`` (z. B. als liegengebliebene ``.tmp``-Datei mit Secrets)
    nie kurzzeitig unter dem Prozess-Umask (typ. 0o644, welt-/gruppenlesbar)
    existiert; für .env wird zusätzlich das Ziel danach separat
    ``chmod 0o600`` gesetzt (siehe :func:`envtool.write_env`).

    Aufrufer muss das Verzeichnis vorher anlegen (``mkdir(parents=True, …)``).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


@dataclass
class BestandConfig:
    """Voller Config-Stand (alle Keys), wie in der Datei abgelegt.

    ``mappings`` bleibt ein uninterpretierter JSON-Wert (Liste von Dicts); der
    Launcher schreibt ihn unangetastet zurück. ``raw`` ist der komplette Satz
    zusätzlicher/Unbekannter Keys, damit ein Rückschreiben keine Felder verliert.
    """

    excel_file: str | None
    sheet_name: str | None
    safety_stock: int
    match_overrides: dict[str, str]
    mappings: object = None
    raw: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        """Baut das Dict für ``json.dump`` (kanonische Key-Reihenfolge)."""
        out: dict = {
            "excel_file": self.excel_file,
            "sheet_name": self.sheet_name,
            "safety_stock": self.safety_stock,
            "match_overrides": self.match_overrides,
        }
        if self.mappings is not None:
            out["mappings"] = self.mappings
        # Unbekannte Keys unverändert anhängen (vorwärtskompatibel).
        for k, v in self.raw.items():
            out.setdefault(k, v)
        return out


def _load_raw(path: Path) -> dict:
    """Liest die config.json; ``{}`` bei fehlender/leerer Datei.

    Kaputte JSON-Antwort ist ein legitimer Fehler (Aufrufer sieht Syntax-Fehler)
    — stillschweigend ignorieren würde einen halben Config-Stand ergeben.
    """
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_config(path: Path | None = None) -> BestandConfig:
    """Liest die config.json in ein :class:`BestandConfig`.

    ``path`` defaultet auf den kanonischen Pfad im ausleihe-api-Repo. Fehlt die
    Datei (Repo noch nicht geklont), gelten die Defaults (safety_stock=5,
    match_overrides={}) — der Tab bleibt bedienbar, schreibt aber erst beim
    Speichern eine neue Datei.
    """
    if path is None:
        path = bestand.config_path()
    data = _load_raw(path)
    safety = data.get("safety_stock", DEFAULT_SAFETY_STOCK)
    if not isinstance(safety, int) or isinstance(safety, bool) or safety < 0:
        # Negativ/ungültig wie das Skript abweisen, aber hier noch nicht raise —
        # erst beim Schreiben validieren (lesen darf nicht crashen).
        safety = DEFAULT_SAFETY_STOCK
    overrides = data.get("match_overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
    # Bekannte Keys abspalten; Rest landet in ``raw`` (vorwärtskompatibel).
    known = {"excel_file", "sheet_name", "safety_stock", "match_overrides", "mappings"}
    raw = {k: v for k, v in data.items() if k not in known}
    return BestandConfig(
        excel_file=data.get("excel_file"),
        sheet_name=data.get("sheet_name"),
        safety_stock=safety,
        match_overrides=dict(overrides),
        mappings=data.get("mappings"),
        raw=raw,
    )


def read_editable(path: Path | None = None) -> BestandConfig:
    """Liefert den Config-Stand für den Roh-Editor (Alias, semantisch gleich).

    Entspricht :func:`read_config`; der Name verdeutlicht am Aufrufort, dass
    nur ``safety_stock`` + ``match_overrides`` editierbar sind.
    """
    return read_config(path)


def write_config(config: BestandConfig, path: Path | None = None) -> Path:
    """Schreibt ``config`` als formatierte JSON-Datei; liefert den Pfad.

    Legt das Verzeichnis bei Bedarf an (z. B. wenn das Repo gerade geklont
    wurde, die config.json aber (noch) fehlt). Formatierung: 2-Space-Indent,
    ``ensure_ascii=False`` — wie die vorgegebene Bestand-config.json.
    """
    if path is None:
        path = bestand.config_path()
    validate_editable(config.safety_stock, config.match_overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        path,
        json.dumps(config.to_json(), indent=2, ensure_ascii=False) + "\n",
    )
    return path


def write_editable(
    safety_stock: int,
    match_overrides: dict[str, str],
    path: Path | None = None,
) -> Path:
    """Setzt ``safety_stock`` + ``match_overrides`` und erhält alle anderen Keys.

    Lädt die bestehende config.json, überschreibt nur die beiden Felder und
    schreibt zurück — so gehen ``excel_file``, ``sheet_name`` und ``mappings``
    nicht verloren, auch wenn der Roh-Editor sie nicht anzeigt.
    """
    if path is None:
        path = bestand.config_path()
    config = read_config(path)
    config.safety_stock = safety_stock
    config.match_overrides = match_overrides
    return write_config(config, path)


# --- Validierung (gespiegelt aus update_bestand_auto.py) --------------------


class ConfigError(ValueError):
    """Validierungsfehler der Bestand-config (safety_stock / match_overrides)."""


def validate_editable(safety_stock: int, match_overrides: dict[str, str]) -> None:
    """Prüft die editierbaren Felder; wirft :class:`ConfigError` bei Verstoß.

    Spiegelt die Prüfung aus ``update_bestand_auto.py``: safety_stock muss ein
    nicht-negativer int sein; match_overrides ein Dict aus String-Key→ISBN-String.
    """
    if isinstance(safety_stock, bool) or not isinstance(safety_stock, int):
        raise ConfigError("safety_stock muss eine ganze Zahl sein.")
    if safety_stock < 0:
        raise ConfigError("safety_stock darf nicht negativ sein.")
    if not isinstance(match_overrides, dict):
        raise ConfigError("match_overrides muss ein Objekt sein.")
    for key, value in match_overrides.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError(
                "match_overrides muss String-Schlüssel und ISBN-String-Werte haben."
            )


def parse_match_overrides_text(text: str) -> dict[str, str]:
    """Parst den Roh-Editor-Text als JSON-Objekt → ``{key: isbn}``.

    Der Roh-Editor zeigt ``match_overrides`` als JSON-Text (z. B.
    ``{"5|Deutsch|": "978..."}``). Wirft :class:`ConfigError` bei Syntax-Fehler
    oder falschem Typ — die GUI zeigt die Nachricht im LogView.
    """
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ConfigError(f"match_overrides: kein gültiges JSON ({e.msg}).") from e
    if not isinstance(data, dict):
        raise ConfigError("match_overrides: oberste Ebene muss ein Objekt {…} sein.")
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ConfigError(
                "match_overrides: Schlüssel und Werte müssen Strings sein."
            )
        out[key] = value
    return out


def format_match_overrides(overrides: dict[str, str]) -> str:
    """Formatiert ``match_overrides`` als hübsches JSON für den Roh-Editor."""
    return json.dumps(overrides, indent=2, ensure_ascii=False, sort_keys=True)
