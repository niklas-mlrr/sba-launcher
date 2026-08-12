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

- **Phase 0** — Gerüst (Repo, Start-Skripte, `core/paths`+`prereqs`+`envtool`,
  minimales GUI-Fenster mit vier Tabs).
- **Phase 1** — Tab ausleihe-ausgabe: clone/update/start/stop + Log-View +
  Host-öffnen + zentrale `.env`-Form.
- **Phase 2** — Tab Barcode-Scanner: clone/update/start/stop (zwei Subprozesse:
  Node-Server + Python-Client) + QR-View (grafisch via `qrcode[pil]` aus der
  geparsten Scanner-URL, ASCII-QR zusätzlich im Log) + portables Node-Bootstrap
  (LTS v22.23.2, Download+Entpacken bei Bedarf).
- **Phase 3** — Tab Bestand MVP: Excel auswählen, Dry-run/echter Lauf (mit
  Bestätigung), `safety_stock` + `match_overrides` als Roh-Editor, Report im
  Log-View. `core/bestand.py` shellt `update_bestand_auto.py` im eigenen
  `.venv-bestand` (GET-only); `install` klont nur `ausleihe-api`. 135 Unit-Tests grün.
- Katalog-Voll-Editor + Hilfe/Polish folgen in den Phasen 4–5
  (siehe Plan `~/.claude/plans/scalable-watching-starlight.md`).

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