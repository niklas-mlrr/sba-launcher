""".env-Lese/Schreib-Helfer für die Geschwister-Repos.

Eine zentrale Form (ISERV_DOMAIN, ISERV_USERNAME, ISERV_PASSWORD, HOST_PASSWORD)
schreibt **beide** ``.env``-Dateien:

- ``ausleihe-ausgabe/.env`` — ISERV_* + HOST_PASSWORD
- ``ausleihe-api/.env`` — nur ISERV_* (HOST_PASSWORD ist ein Host-Konzept)

Produktionsschutz (CLAUDE.md):
- Passwörter werden **nie** geloggt. Die GUI maskiert sensible Felder selbst
  über die Widget-Konfiguration (``FormField(masked=True)`` / ``show='*'``);
  ``write_env`` nimmt Klartextwerte nur aus dem übergebenen Dict, nie aus
  Logs/CLI-Args.
- Vorhandene ``.env``-Dateien werden **zeilenerhaltend** aktualisiert — Kommentare
  und optionale Schlüssel (PORT, WORKER_CONTEXTS, PRINT_BACKEND, …) bleiben
  stehen; nur die Form-Schlüssel werden gesetzt.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from core import paths
from core.config_io import _atomic_write_text

# Alle Form-Schlüssel (Reihenfolge = Form-Reihenfolge).
ENV_FORM_KEYS: tuple[str, ...] = (
    "ISERV_DOMAIN",
    "ISERV_USERNAME",
    "ISERV_PASSWORD",
    "HOST_PASSWORD",
)

# (key, deutsches Label, maskiert) — einzige Quelle für die GUI-Form
# (``gui/tab_ausleihe.py`` + der Ersteinrichtungs-Assistent ``gui/setup_wizard.py``
# teilen sich diese Definition, statt sie zu duplizieren).
FORM_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("ISERV_DOMAIN", "IServ-Adresse", False),
    ("ISERV_USERNAME", "IServ-Benutzername", False),
    ("ISERV_PASSWORD", "IServ-Passwort", True),
    ("HOST_PASSWORD", "Passwort fürs Arbeitsfenster", True),
)

# Welche Schlüssel in welche Repo-.env gehören.
# HOST_PASSWORD ist ein Host-Konzept von ausleihe-ausgabe; ausleihe-api kennt es nicht.
REPO_KEYS: dict[str, tuple[str, ...]] = {
    "ausleihe-ausgabe": (
        "ISERV_DOMAIN",
        "ISERV_USERNAME",
        "ISERV_PASSWORD",
        "HOST_PASSWORD",
    ),
    "ausleihe-api": (
        "ISERV_DOMAIN",
        "ISERV_USERNAME",
        "ISERV_PASSWORD",
    ),
}

# Schlüssel, deren Werte in der Anzeige maskiert werden (niemals loggen).
SENSITIVE_KEYS: frozenset[str] = frozenset({"ISERV_PASSWORD", "HOST_PASSWORD"})

# ``KEY=value`` (Wert darf ``=`` enthalten). Export-Prefix optional.
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env_text(text: str) -> dict[str, str]:
    """Parst ``KEY=value``-Zeilen; Kommentare/Leerzeilen werden ignoriert.

    Kein Quoting-Strip — Werte stehen 1:1 (inkl. eventueller Quotes). Reicht für
    die Form-Schlüssel (Pfade, Passwörter ohne Quotes). Der letzte Wert eines
    Schlüssels gewinnt (Shell-Semantik).

    Sensible Schlüssel (siehe :data:`SENSITIVE_KEYS`) werden **nicht** am
    Inline-Kommentar `` #`` abgespalten — ein Passwort, das `` #`` enthält,
    würde sonst verstümmelt. Secrets mit führenden/trailingen Leerzeichen müssen
    gequotet werden (``KEY="value with #"``), da Quotes hier nicht gestrippt
    werden (Best-Effort, keine vollständige Shell-Quoting-Engine).
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        # Inline-Kommentar nur abheben, wenn ein Whitespace vor ``#`` steht UND
        # der Wert nicht mit einem Quote beginnt — außer für sensible Schlüssel
        # (Passwörter), bei denen `` #`` Teil des Werts sein kann.
        if (
            key not in SENSITIVE_KEYS
            and value
            and value[0] not in "\"'"
            and " #" in value
        ):
            value = value.split(" #", 1)[0].rstrip()
        out[key] = value
    return out


def read_env(path: Path) -> dict[str, str]:
    """Liest eine ``.env``-Datei; leer/fehlt → ``{}``."""
    if not path.is_file():
        return {}
    return parse_env_text(path.read_text(encoding="utf-8"))


def _update_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    """Ersetzt ``KEY=…``-Zeilen in ``lines``; nicht vorhandene werden angehängt.

    Erhält alle anderen Zeilen (Kommentare, Leer, optionale Schlüssel) 1:1.
    """
    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        m = _LINE_RE.match(line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            result.append(f"{key}={remaining[key]}")
            del remaining[key]
        else:
            result.append(line)
    # Neue Schlüssel ans Ende (ohne Kommentar-Schmuck, klar getrennt).
    for key, value in remaining.items():
        result.append(f"{key}={value}")
    return result


def write_env(path: Path, updates: dict[str, str]) -> None:
    """Schreibt ``updates`` in ``path``; vorhandene Zeilen/Keys bleiben erhalten.

    Existiert die Datei nicht, wird sie neu angelegt (nur die ``updates``-Keys).
    Verzeichnis wird bei Bedarf mit erstellt (z. B. wenn das Repo gerade geklont
    wurde, aber die .env noch fehlt).

    Atomar via Temp-Datei + ``os.replace`` (kein halbfertiger Zustand bei
    Absturz). Da ``.env`` Passwörter enthält, wird danach ``chmod 0o600``
    gesetzt (nur Owner-lesbar) — auf Windows/ACL-FS ist das ein No-op.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    # ``None``-Werte nicht als Literal-String "None" schreiben — als leerer
    # String behandeln (löscht den Wert, nicht die Zeile; siehe write_form).
    updates = {k: ("" if v is None else str(v)) for k, v in updates.items()}
    new_lines = _update_lines(lines, updates)
    # Erzwinge abschließenden Zeilenumbruch (saubere Datei).
    text = "\n".join(new_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    _atomic_write_text(path, text)
    # .env enthält Passwörter → restriktive Permissions (nur Owner). Auf
    # Windows/ACL- oder Read-only-FS ist chmod nicht anwendbar — no-op.
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def read_form() -> dict[str, str]:
    """Liest die Form-Werte aus den bestehenden ``.env``-Dateien.

    Vorrang: ``ausleihe-ausgabe/.env`` (enthält HOST_PASSWORD und ISERV_*).
    Fehlt sie (Repo noch nicht geklont / .env fehlt), fällt IServ auf
    ``ausleihe-api/.env`` zurück. Fehlen beide, sind die Werte leer.

    Liefert **alle** :data:`ENV_FORM_KEYS`, ggf. mit leeren Strings.
    """
    aa = read_env(paths.env_file("ausleihe-ausgabe"))
    api = read_env(paths.env_file("ausleihe-api"))
    form: dict[str, str] = {}
    for key in ENV_FORM_KEYS:
        if key in aa:
            form[key] = aa[key]
        elif key in api:
            form[key] = api[key]
        else:
            form[key] = ""
    return form


def write_form(values: dict[str, str]) -> dict[str, Path]:
    """Schreibt die Form-Werte in **beide** ``.env``-Dateien.

    Nur die für das Repo zulässigen Schlüssel werden geschrieben
    (siehe :data:`REPO_KEYS`); unbekannte/leere Werte werden als leerer String
    gesetzt (löscht also einen Wert, nicht die Zeile — Entfernen ist selten
    gewollt und sonst im Editor sichtbar).

    Liefert die geschriebenen Pfade (für eine Bestätigung in der GUI).
    """
    written: dict[str, Path] = {}
    for repo, keys in REPO_KEYS.items():
        updates = {
            k: ("" if (v := values.get(k, "")) is None else str(v)) for k in keys
        }
        path = paths.env_file(repo)
        write_env(path, updates)
        written[repo] = path
    return written


def defaults_from_example(repo: str) -> dict[str, str]:
    """Liest ``.env.example`` eines Repos als Default-Quelle (z. B. DOMAIN).

    Liefert nur die Form-Schlüssel, die in der Example vorgegeben sind
    (ISERV_DOMAIN ist dort oft gesetzt). Passwörter sind leer — nie erraten.
    """
    example = paths.sibling(repo) / ".env.example"
    if not example.is_file():
        return {}
    parsed = parse_env_text(example.read_text(encoding="utf-8"))
    allowed = REPO_KEYS.get(repo, ())
    return {k: parsed.get(k, "") for k in allowed}


def is_ready(repo: str = "ausleihe-ausgabe") -> bool:
    """Prüft, ob ``repo`` startklar ist (``.env`` existiert + alle Keys belegt).

    Genutzt von Wave-2 (``status.py``, ``tab_ausleihe.py``) um zu entscheiden, ob
    der Tab/Start aktiviert wird. Liefert ``True`` gdw. die ``.env`` für ``repo``
    existiert **und** jeder in :data:`REPO_KEYS[repo]` gelistete Schlüssel einen
    nicht-leeren Wert hat (Whitespace-only gilt als leer).

    Für ``ausleihe-ausgabe`` sind das ``ISERV_DOMAIN``, ``ISERV_USERNAME``,
    ``ISERV_PASSWORD`` und ``HOST_PASSWORD``; für ``ausleihe-api`` entfällt
    ``HOST_PASSWORD``. Die konkrete Menge ergibt sich aus :data:`REPO_KEYS`
    (Single Source of Truth) — unbekannte ``repo`` liefern ``False``.
    """
    required = REPO_KEYS.get(repo, ())
    if not required:
        return False
    env_path = paths.env_file(repo)
    if not env_path.is_file():
        return False
    values = read_env(env_path)
    return all(values.get(k, "").strip() != "" for k in required)
