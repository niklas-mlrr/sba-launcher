# SBA-Launcher

Zentrale GUI für die drei SBA-Werkzeuge der Schulbuchausleihe:

- **ausleihe-ausgabe** — Handy-Scanner für Stapelerstellung (Modus A) + Live-Ausgabe (Modus B). Python/uv, FastAPI, Playwright.
- **Bestand-/Nachbestellungs-Excel** — aktualisiert die Bestandsliste aus IServ (read-only GET). Python, openpyxl, `ausleihe-api[bestand]`.
- **barcode-simple** — eigenständiger Barcode-Scanner (Node.js-Server + Python-Client).

Der Launcher installiert, updated, startet und stopt diese Werkzeuge für
nicht-technische Nachfolger im Ausleihe-Team, sobald die ursprünglichen
Entwickler die Schule verlassen haben. Dazu ein Bestand-Katalog-Editor
(Fach × Jahrgang → ISBN, Mehrjahresband).

## Status

Phase 0 — Gerüst (Repo, Start-Skripte, core-Pfade/.env-IO, minimales GUI-Fenster
mit vier Tabs). Klonen/Starten/Bestand/Editor folgen in den Phasen 1–5
(siehe Plan in `~/projects/sba/sba-launcher`/`docs`).

## Architektur

- **`core/`** — Orchestrierungslogik (Git, uv, npm, Subprocess, .env-IO, Katalog),
  **ohne Tkinter-Import**, voll unit-testbar auf dem headless VPS via
  `uv run pytest`.
- **`gui/`** — dünne Tkinter-Bindings an `core/`-Funktionen; manuell auf dem
  Windows-Laptop gesmoket.

Ziel-Layout auf dem Ausleihe-Laptop (`C:\SBA\`):

```
C:\SBA\
├── sba-launcher\        ← dieses Repo (start.bat, launcher.py)
├── ausleihe-ausgabe\    ← vom Launcher geklont
├── ausleihe-api\        ← vom Launcher geklont
└── barcode-simple\      ← vom Launcher geklont
```

Der Launcher referenziert Geschwister via `../<repo>` relativ zum eigenen Root
(`core/paths.py`) — gleiche Konvention wie das Bestand-Projekt.

## Start (Windows)

```
start.bat
```

Bootet `uv` (falls fehlt), installiert Abhängigkeiten, öffnet das Launcher-Fenster.

## Dev (VPS, headless)

```
uv sync
uv run pytest        # core-Tests, tkinter-frei
```

GUI nicht testbar ohne Display; `core/` bleibt tk-frei gerade dafür.

## Produktionsschutz

- Der Launcher führt **keine** IServ-Schreibzugriffe aus (nur GET via `ausleihe-api`,
  `allow_writes=False`).
- `ALLOW_BOOKING` wird **nicht** umgeschaltet; der Help-Tab dokumentiert die Regel.
- IServ-Passwörter werden nie geloggt; `.env`-Werte via Subprocess-Umgebung, nicht
  via CLI-Args. Siehe `ausleihe-ausgabe/CLAUDE.md` für die vollständigen Regeln.