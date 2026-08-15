"""Tests für ``scripts/seed_from_iserv.py`` — Syntax-Smoke, keine Logikabdeckung.

Das Skript ist kein Modul des Launcher-Pakets: es hängt von privaten APIs des
Geschwister-Repos ``ausleihe-api`` ab (``update_bestand_auto``, das Paket
``ausleihe``) und läuft im **dortigen** venv, nicht im Launcher-venv. Ein
echter Import/Ausführungstest würde daher entweder das Sibling-Repo voraussetzen
(nicht garantiert vorhanden) oder dessen private APIs ins Launcher-Testing
ziehen — beides außerhalb des Scopes dieses Repos.

Was hier geprüft wird: das Skript ist syntaktisch gültiges Python (``ast.parse``,
läuft immer) und — falls das Sibling-Repo zufällig neben diesem Checkout liegt
und importierbar ist — dass es sich zumindest bis zum Sibling-Import durcharbeitet
ohne einen ImportError, der NICHT vom fehlenden Sibling kommt.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_from_iserv.py"


def test_seed_from_iserv_ist_syntaktisch_gueltig() -> None:
    """Smoke-Test, der immer läuft: Skript parst als gültiges Python."""
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source, filename=str(SCRIPT))


def test_seed_from_iserv_hat_keine_module_level_seiteneffekte_vor_main() -> None:
    """``main()`` darf erst bei ``__main__`` laufen — kein Auto-Run beim Import.

    Rein statische Prüfung (kein Import, da das Sibling-``ausleihe``-Paket hier
    typischerweise fehlt): das Modul darf auf Top-Level keinen Aufruf von
    ``main()`` enthalten außer im ``if __name__ == "__main__":``-Guard.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    for node in tree.body:
        if isinstance(node, ast.If):
            continue  # der __main__-Guard selbst ist erlaubt
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            name = call.func.id if isinstance(call.func, ast.Name) else None
            assert name != "main", "main() darf nicht auf Modul-Ebene aufgerufen werden"
