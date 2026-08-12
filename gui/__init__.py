"""SBA-Launcher GUI — dünne Tkinter-Bindings an ``core/``.

Phase 0: nur das Fenster-Gerüst mit vier Tabs, ohne echte Logik. Die Tabs
werden in Phase 1–4 mit Aktionen bestückt. ``gui/`` darf Tkinter importieren
(nicht auf dem headless VPS testbar); ``core/`` bleibt tk-frei.
"""
