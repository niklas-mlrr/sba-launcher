#!/usr/bin/env python3
"""SBA-Launcher — Tkinter-Entry (dünn).

Startet die GUI aus ``gui/app.py``. Keine eigene Logik; dieser Datei-Punkt ist
was ``start.bat`` (``uv run python launcher.py``) aufruft. Bewusst klein, damit
die Logik in testbaren Modulen lebt.
"""

from __future__ import annotations

from gui.app import main

if __name__ == "__main__":
    main()
