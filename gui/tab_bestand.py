"""Tab: Bestand (dünn — alle Logik in ``core.bestand`` + ``core.config_io``).

Phase-3-MVP: Excel auswählen → dry-run/echter Lauf (mit Bestätigung) → Report
im LogView. Config-Roh-Editor für ``safety_stock`` + ``match_overrides``
(JSON-Text); speichert über ``config_io.write_editable`` und erhält alle anderen
Keys (``excel_file``, ``sheet_name``, ``mappings``). Der Voll-Katalog-Editor
(Fach × Jahrgang) folgt in Phase 4.

Dünne GUI-Regel: Install/Update/Run laufen in Hintergrund-Threads; deren
``log``-Callback hängt Zeilen thread-safe via ``after(0, …)`` ins LogView.
Bestand ist ein Ein-Schuss-Skript (kein dauerhafter Subprocess) — im Gegensatz
zum Barcode-Tab gibt es hier keinen ``SubprocessManager``-Poll-Loop.

Produktionsschutz: ``run_auto`` ist reiner GET-Pfad (schreibt nur in die Excel,
nie nach IServ). Ein echter Lauf (ohne ``--dry-run``) verlangt eine explizite
Bestätigung (``messagebox.askyesno``) — die Excel wird überschrieben (mit
Backup). ``ALLOW_BOOKING``/API-Writes werden nicht angeboten.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import bestand as bst
from core import config_io, gitops
from gui.widgets import LogView

# Fenster-Titel für filedialog (Windows-orientiert, spielt auf POSIX keine Rolle).
_EXCEL_FILETYPES = [("Excel-Dateien", "*.xlsx"), ("Alle Dateien", "*.*")]


class BestandTab(ttk.Frame):
    """Tab-Oberfläche für die Bestand-/Nachbestellungs-Excel."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._busy = False
        self._excel_path: Path | None = None
        self._build()
        self._load_config_into_form()
        self._refresh_status()

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        # Oben: Installieren/Updaten + Status.
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self._btn_install = ttk.Button(top, text="Installieren", command=self.on_install)
        self._btn_install.pack(side="left", padx=(0, 4))
        self._btn_update = ttk.Button(top, text="Updaten", command=self.on_update)
        self._btn_update.pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self._btn_dryrun = ttk.Button(top, text="Dry-run", command=self.on_dry_run)
        self._btn_dryrun.pack(side="left", padx=4)
        self._btn_real = ttk.Button(top, text="Echt ausführen", command=self.on_real_run)
        self._btn_real.pack(side="left", padx=4)
        self._status = ttk.Label(top, text="…")
        self._status.pack(side="right")

        # Excel-Auswahlzeile.
        excel_row = ttk.Frame(self)
        excel_row.pack(fill="x", padx=12, pady=(4, 0))
        ttk.Label(excel_row, text="Excel-Datei:", width=14, anchor="w").pack(side="left")
        self._excel_var = tk.StringVar(value="(keine ausgewählt)")
        ttk.Label(excel_row, textvariable=self._excel_var, anchor="w").pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        self._btn_pick = ttk.Button(excel_row, text="…", width=3, command=self.on_pick_excel)
        self._btn_pick.pack(side="left")

        # Mittelteil: links Config-Editor + Report, daneben Schuljahr.
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=4)

        # Config-Roh-Editor (links, oberer Bereich).
        cfg = ttk.LabelFrame(mid, text="Config (Roh-Editor)")
        cfg.pack(fill="x", pady=(0, 4))

        ss_row = ttk.Frame(cfg)
        ss_row.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(ss_row, text="Sicherheitsbestand:", width=22, anchor="w").pack(side="left")
        self._safety_var = tk.StringVar()
        ttk.Entry(ss_row, textvariable=self._safety_var, width=8).pack(side="left")

        ov_row = ttk.Frame(cfg)
        ov_row.pack(fill="both", padx=8, pady=2)
        ov_lbl = ttk.Label(
            ov_row, text="match_overrides\n(JSON):", width=22, anchor="nw", justify="left"
        )
        ov_lbl.pack(side="left")
        self._overrides_text = tk.Text(ov_row, height=6, width=48, font=("TkFixedFont",))
        self._overrides_text.pack(side="left", fill="x", expand=True)

        cfg_btns = ttk.Frame(cfg)
        cfg_btns.pack(fill="x", padx=8, pady=(4, 8))
        self._btn_save_cfg = ttk.Button(
            cfg_btns, text="Config speichern", command=self.on_save_config
        )
        self._btn_save_cfg.pack(side="left")
        self._btn_reload_cfg = ttk.Button(
            cfg_btns, text="Config neu laden", command=self._load_config_into_form
        )
        self._btn_reload_cfg.pack(side="left", padx=4)

        # Schuljahr (optional, frei gelassen = aktuelles).
        sy_row = ttk.Frame(mid)
        sy_row.pack(fill="x", pady=(0, 4))
        ttk.Label(sy_row, text="Schuljahr (optional):", width=22, anchor="w").pack(side="left")
        self._schoolyear_var = tk.StringVar()
        ttk.Entry(sy_row, textvariable=self._schoolyear_var, width=14).pack(side="left")
        ttk.Label(sy_row, text='z. B. "2025/2026"; leer = aktuelles', foreground="#888").pack(
            side="left", padx=8
        )

        # Report-Log (unten, füllt den Rest).
        self._log = LogView(mid, height=16)
        self._log.pack(fill="both", expand=True)
        self._log.append(
            "Bereit. Erst 'Installieren' (klont ausleihe-api + Bestand-Venv), dann "
            "Excel-Datei wählen und 'Dry-run' (schreibt nichts) oder 'Echt ausführen'."
        )
        self._log.append(
            "Hinweis: Echter Lauf überschreibt die Excel (mit Backup) — nur nach "
            "Prüfung des Dry-run-Reports. IServ-Kontakt ist rein lesend (GET)."
        )

    # --- Config laden/speichern --------------------------------------------

    def _load_config_into_form(self) -> None:
        """Liest ``config.json`` (Defaults bei Fehlen) ins Formular."""
        try:
            cfg = config_io.read_editable()
        except Exception as e:  # noqa: BLE001 — kaputte JSON soll GUI nicht crashen
            self._log.append(f"[Config] Lesen fehlgeschlagen: {e}")
            return
        self._safety_var.set(str(cfg.safety_stock))
        self._overrides_text.delete("1.0", "end")
        self._overrides_text.insert("1.0", config_io.format_match_overrides(cfg.match_overrides))

    def on_save_config(self) -> None:
        """Validiert + speichert safety_stock + match_overrides (erhält Rest)."""
        try:
            safety = int(self._safety_var.get().strip())
        except ValueError:
            messagebox.showerror("Config", "Sicherheitsbestand muss eine ganze Zahl sein.")
            return
        try:
            overrides = config_io.parse_match_overrides_text(
                self._overrides_text.get("1.0", "end")
            )
        except config_io.ConfigError as e:
            messagebox.showerror("Config", str(e))
            return
        try:
            path = config_io.write_editable(safety, overrides)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Config", f"Speichern fehlgeschlagen: {e}")
            return
        self._log.append(f"[Config] gespeichert: {path}")

    # --- Excel-Auswahl -----------------------------------------------------

    def on_pick_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Bestand-Excel wählen", filetypes=_EXCEL_FILETYPES
        )
        if path:
            self._excel_path = Path(path)
            self._excel_var.set(str(self._excel_path))

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Installieren", bst.install)

    def on_update(self) -> None:
        self._run_async("Updaten", bst.update)

    def on_dry_run(self) -> None:
        self._run_run(dry_run=True)

    def on_real_run(self) -> None:
        ok = messagebox.askyesno(
            "Echt ausführen?",
            "Ohne --dry-run wird die Excel-Datei überschrieben (es wird ein "
            "Backup im Unterordner 'backups' angelegt).\n\n"
            "Vorher den Dry-run-Report prüfen!\n\nFortfahren?",
            icon="warning",
        )
        if not ok:
            return
        self._run_run(dry_run=False)

    def _run_run(self, dry_run: bool) -> None:
        """Startet ``run_auto`` (dry-run oder echt) im Hintergrund-Thread."""
        if self._busy:
            return
        excel = self._excel_path
        if excel is None:
            messagebox.showinfo("Excel", "Bitte erst eine Excel-Datei auswählen.")
            return
        schoolyear = self._schoolyear_var.get().strip() or None
        label = "Dry-run" if dry_run else "Echt ausführen"

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                rc = bst.run_auto(
                    dry_run=dry_run, excel=excel, schoolyear=schoolyear, log=log
                )
                tag = "[Dry-run]" if dry_run else "[Echt]"
                if rc == 0:
                    self.after(0, lambda: self._log.append(f"{tag} fertig (Exit 0)."))
                else:
                    self.after(
                        0, lambda: self._log.append(f"{tag} beendet mit Fehlern (Exit {rc}).")
                    )
            except Exception as e:  # noqa: BLE001
                msg = f"[{label} FEHLER] {e}"
                self.after(0, lambda: self._log.append(msg))
            finally:
                self.after(0, self._end_busy)

        self._begin_busy(label)
        threading.Thread(target=worker, daemon=True).start()

    def _run_async(self, label: str, fn) -> None:
        """``fn(log)`` im Hintergrund-Thread (Install/Update)."""
        if self._busy:
            return

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                fn(log)
                self.after(0, lambda: self._log.append(f"[{label}] fertig."))
            except Exception as e:  # noqa: BLE001
                msg = f"[{label} FEHLER] {e}"
                self.after(0, lambda: self._log.append(msg))
            finally:
                self.after(0, self._end_busy)

        self._begin_busy(label)
        threading.Thread(target=worker, daemon=True).start()

    # --- Busy-Status -------------------------------------------------------

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_dryrun, self._btn_real):
            b.state(["disabled"])
        self._status.configure(text=f"{label} …")

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update, self._btn_dryrun, self._btn_real):
            b.state(["!disabled"])
        self._refresh_status()

    # --- Status ------------------------------------------------------------

    def _refresh_status(self) -> None:
        """Git-Status von ausleihe-api + Venv-Existenz."""
        st = gitops.status("ausleihe-api")
        if not st.installed:
            repo = "ausleihe-api: fehlt"
        else:
            dirty = " (dirty)" if st.dirty else ""
            repo = f"ausleihe-api: {st.branch or '?'}{dirty}"
        parts = [repo]
        if bst.bestand_venv_python().is_file():
            parts.append("Venv ok")
        else:
            parts.append("Venv fehlt")
        self._status.configure(text="  |  ".join(parts))


def build(parent: tk.Widget) -> BestandTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return BestandTab(parent)
