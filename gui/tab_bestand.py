"""Tab: Bestand (dünn — alle Logik in ``core.bestand`` + ``core.config_io`` +
``core.catalog``).

Phase 3: Excel auswählen → dry-run/echter Lauf (mit Bestätigung) → Report im
LogView. Config-Roh-Editor für ``safety_stock`` + ``match_overrides`` (JSON-Text);
speichert über ``config_io.write_editable`` und erhält alle anderen Keys
(``excel_file``, ``sheet_name``, ``mappings``).

Phase 4 — Voll-Katalog-Editor: ``ttk.Treeview`` (Fach × Jahrgang → ISBN,
Mehrjahresband, Titel/Verlag/Neupreis) mit Hinzufügen/Entfernen/Bearbeiten,
Import aus Excel, Excel aus Vorlage (Mappings-only) und Override-Sync aus dem
Katalog. Der Roh-Editor bleibt als „Erweitert"-Fallback darunter.

Dünne GUI-Regel: Install/Update/Run laufen in Hintergrund-Threads; deren
``log``-Callback hängt Zeilen thread-safe via ``after(0, …)`` ins LogView.
Bestand ist ein Ein-Schuss-Skript (kein dauerhafter Subprocess) — im Gegensatz
zum Barcode-Tab gibt es hier keinen ``SubprocessManager``-Poll-Loop. Katalog-
Aktionen sind lokale Datei-IO (kein IServ-Kontakt) und laufen direkt im Thread.

Produktionsschutz: ``run_auto`` ist reiner GET-Pfad (schreibt nur in die Excel,
nie nach IServ). Ein echter Lauf (ohne ``--dry-run``) verlangt eine explizite
Bestätigung (``messagebox.askyesno``) — die Excel wird überschrieben (mit
Backup). ``ALLOW_BOOKING``/API-Writes werden nicht angeboten. Der Katalog-Editor
ist rein lokale Excel-/JSON-IO.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import bestand as bst
from core import catalog, config_io, gitops
from gui.widgets import LogView

# Fenster-Titel für filedialog (Windows-orientiert, spielt auf POSIX keine Rolle).
_EXCEL_FILETYPES = [("Excel-Dateien", "*.xlsx"), ("Alle Dateien", "*.*")]

# Treeview-Spalten (id wird als iid genutzt, nicht als Anzeigespalte).
_KAT_COLUMNS = ("fach", "hint", "von", "bis", "isbn", "titel", "verlag", "neupreis", "mjb")
_KAT_HEADERS = {
    "fach": "Fach",
    "hint": "Hint",
    "von": "Von",
    "bis": "Bis",
    "isbn": "ISBN",
    "titel": "Titel",
    "verlag": "Verlag",
    "neupreis": "Neupreis",
    "mjb": "MJB",
}


class BestandTab(ttk.Frame):
    """Tab-Oberfläche für die Bestand-/Nachbestellungs-Excel."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._busy = False
        self._excel_path: Path | None = None
        self._katalog: catalog.Katalog = catalog.Katalog(schule="", schuljahr="")
        self._build()
        self._load_config_into_form()
        self._load_katalog()
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

        # Mittelteil: Katalog-Editor (oben), Config-Roh-Editor (Erweitert),
        # Schuljahr, Report-Log (unten).
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=4)

        # ── Katalog-Editor (Treeview) ──────────────────────────────────────
        kat = ttk.LabelFrame(mid, text="Katalog (Fach × Jahrgang → ISBN)")
        kat.pack(fill="both", expand=True, pady=(0, 4))

        tree_row = ttk.Frame(kat)
        tree_row.pack(fill="both", expand=True, padx=8, pady=(8, 2))
        self._tree = ttk.Treeview(
            tree_row, columns=_KAT_COLUMNS, show="headings", height=9
        )
        for col in _KAT_COLUMNS:
            self._tree.heading(col, text=_KAT_HEADERS[col])
            self._tree.column(col, width=90, stretch=True)
        self._tree.column("fach", width=120, stretch=False)
        self._tree.column("titel", width=220, stretch=True)
        self._tree.column("isbn", width=130, stretch=False)
        self._tree.column("hint", width=70, stretch=False)
        self._tree.column("von", width=40, stretch=False)
        self._tree.column("bis", width=40, stretch=False)
        self._tree.column("mjb", width=40, stretch=False)
        tree_scroll = ttk.Scrollbar(tree_row, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _e: self.on_katalog_edit())

        kat_btns = ttk.Frame(kat)
        kat_btns.pack(fill="x", padx=8, pady=(2, 8))
        for text, cmd in [
            ("Aus Excel importieren", self.on_katalog_import),
            ("Excel aus Vorlage", self.on_katalog_render),
            ("Overrides synchronisieren", self.on_katalog_sync),
            ("Hinzufügen", self.on_katalog_add),
            ("Bearbeiten", self.on_katalog_edit),
            ("Entfernen", self.on_katalog_remove),
            ("Katalog speichern", self.on_katalog_save),
            ("Neu laden", self.on_katalog_reload),
        ]:
            ttk.Button(kat_btns, text=text, command=cmd).pack(side="left", padx=(0, 4))

        # Config-Roh-Editor („Erweitert"-Fallback).
        cfg = ttk.LabelFrame(mid, text="Config (Roh-Editor / Erweitert)")
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

    # --- Katalog-Editor -----------------------------------------------------

    def _load_katalog(self) -> None:
        """Lädt ``data/katalog.json`` (leer bei Fehlen) und befüllt den Treeview."""
        try:
            self._katalog = catalog.load_katalog()
        except Exception as e:  # noqa: BLE001 — kaputte JSON soll GUI nicht crashen
            self._log.append(f"[Katalog] Lesen fehlgeschlagen: {e}")
            self._katalog = catalog.Katalog(schule="", schuljahr="")
        self._populate_tree()

    def _populate_tree(self) -> None:
        """Zeigt ``self._katalog`` im Treeview (sortiert wie der Katalog)."""
        self._tree.delete(*self._tree.get_children())
        for e in self._katalog.eintraege:
            self._tree.insert(
                "",
                "end",
                iid=e.id,
                values=(
                    e.fach,
                    e.hint or "",
                    e.jahrgang_von,
                    e.jahrgang_bis,
                    e.isbn,
                    e.titel,
                    e.verlag,
                    f"{e.neupreis:.2f}" if e.neupreis else "",
                    "✓" if e.mehrjahresband else "",
                ),
            )

    def on_katalog_reload(self) -> None:
        self._load_katalog()
        self._log.append("[Katalog] neu geladen.")

    def on_katalog_save(self) -> None:
        """Schreibt den In-Memory-Katalog nach ``data/katalog.json``."""
        try:
            path = catalog.save_katalog(self._katalog)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Katalog", f"Speichern fehlgeschlagen: {e}")
            return
        self._log.append(f"[Katalog] gespeichert: {path} ({len(self._katalog.eintraege)} Einträge)")

    def on_katalog_import(self) -> None:
        """Importiert eine Bestand-Excel (+ mappings aus config.json) in den Katalog."""
        path = filedialog.askopenfilename(
            title="Bestand-Excel zum Import wählen", filetypes=_EXCEL_FILETYPES
        )
        if not path:
            return

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                cfg = config_io.read_config()
                mappings = cfg.mappings if isinstance(cfg.mappings, list) else []
                kat = catalog.import_from_excel(
                    Path(path), mappings, sheet_name=cfg.sheet_name,
                    schule=self._katalog.schule, schuljahr=self._katalog.schuljahr,
                )
                self._katalog = kat
                self.after(0, self._populate_tree)
                log(f"[Katalog] Import fertig: {len(kat.eintraege)} Einträge aus {path}")
            except Exception as e:  # noqa: BLE001
                log(f"[Katalog] Import fehlgeschlagen: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_katalog_render(self) -> None:
        """Erzeugt eine Excel-Datei aus Vorlage + Katalog (Mappings-only)."""
        template = filedialog.askopenfilename(
            title="Vorlage (.xlsx) wählen", filetypes=_EXCEL_FILETYPES
        )
        if not template:
            return
        out = filedialog.asksaveasfilename(
            title="Ausgabe-Excel speichern unter",
            defaultextension=".xlsx",
            filetypes=_EXCEL_FILETYPES,
        )
        if not out:
            return

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                cfg_path, unmatched = catalog.render_excel(
                    Path(template), self._katalog, Path(out)
                )
                log(f"[Katalog] Excel aus Vorlage: {out}")
                log(f"[Katalog] config.json geschrieben: {cfg_path}")
                if unmatched:
                    log(f"[Katalog] {len(unmatched)} Eintrag/Einträge ohne Layout-Slot:")
                    for u in unmatched:
                        log(f"    - {u}")
                else:
                    log("[Katalog] alle Einträge zugeordnet.")
            except Exception as e:  # noqa: BLE001
                log(f"[Katalog] Excel-aus-Vorlage fehlgeschlagen: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_katalog_sync(self) -> None:
        """Schreibt ``match_overrides`` aus dem Katalog in die config.json."""
        try:
            overrides = catalog.catalog_to_overrides(self._katalog)
            safety = config_io.read_config().safety_stock
            path = config_io.write_editable(safety, overrides)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Overrides", f"Synchronisieren fehlgeschlagen: {e}")
            return
        self._load_config_into_form()
        self._log.append(
            f"[Katalog] {len(overrides)} Overrides synchronisiert nach {path}"
        )

    def on_katalog_add(self) -> None:
        eintrag = self._edit_dialog()
        if eintrag is None:
            return
        self._katalog.eintraege.append(eintrag)
        self._populate_tree()
        self._log.append(
            f"[Katalog] hinzugefügt: {eintrag.fach} "
            f"Jg.{eintrag.jahrgang_von}-{eintrag.jahrgang_bis}"
        )

    def on_katalog_edit(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        eid = sel[0]
        eintrag = next((e for e in self._katalog.eintraege if e.id == eid), None)
        if eintrag is None:
            return
        updated = self._edit_dialog(eintrag)
        if updated is None:
            return
        # Eintrag ersetzen (gleiche ID, falls Identität unverändert).
        idx = self._katalog.eintraege.index(eintrag)
        self._katalog.eintraege[idx] = updated
        self._populate_tree()
        self._log.append(
            f"[Katalog] bearbeitet: {updated.fach} Jg.{updated.jahrgang_von}-{updated.jahrgang_bis}"
        )

    def on_katalog_remove(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        eid = sel[0]
        self._katalog.eintraege = [e for e in self._katalog.eintraege if e.id != eid]
        self._populate_tree()
        self._log.append("[Katalog] Eintrag entfernt (Katalog speichern nicht vergessen).")

    def _edit_dialog(self, eintrag: catalog.Eintrag | None = None) -> catalog.Eintrag | None:
        """Modal-Dialog zum Anlegen/Bearbeiten eines Eintrags; None bei Abbruch."""
        dlg = tk.Toplevel(self)
        dlg.title("Eintrag bearbeiten" if eintrag else "Eintrag hinzufügen")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(True, True)

        fields: dict[str, tk.StringVar] = {}
        e = eintrag or catalog.Eintrag(fach="", jahrgang_von=5, jahrgang_bis=5, isbn="")
        defaults = {
            "Fach": e.fach,
            "Hint": e.hint or "",
            "Von": str(e.jahrgang_von),
            "Bis": str(e.jahrgang_bis),
            "ISBN": e.isbn,
            "Titel": e.titel,
            "Verlag": e.verlag,
            "Neupreis": f"{e.neupreis:.2f}" if e.neupreis else "",
        }
        _keys = ["Fach", "Hint", "Von", "Bis", "ISBN", "Titel", "Verlag", "Neupreis"]
        for i, key in enumerate(_keys):
            ttk.Label(dlg, text=key + ":", width=10, anchor="w").grid(
                row=i, column=0, sticky="w", padx=8, pady=2
            )
            var = tk.StringVar(value=defaults[key])
            ttk.Entry(dlg, textvariable=var, width=40).grid(row=i, column=1, padx=8, pady=2)
            fields[key] = var

        result: dict[str, object] = {"eintrag": None}

        def on_ok() -> None:
            try:
                von = int(fields["Von"].get().strip())
                bis = int(fields["Bis"].get().strip())
            except ValueError:
                messagebox.showerror("Eingabe", "Von/Bis müssen ganze Zahlen sein.", parent=dlg)
                return
            try:
                preis = float(fields["Neupreis"].get().strip() or "0")
            except ValueError:
                messagebox.showerror("Eingabe", "Neupreis muss eine Zahl sein.", parent=dlg)
                return
            hint = fields["Hint"].get().strip() or None
            new = catalog.Eintrag(
                fach=fields["Fach"].get().strip(),
                jahrgang_von=von,
                jahrgang_bis=bis,
                isbn=fields["ISBN"].get().strip(),
                hint=hint,
                titel=fields["Titel"].get().strip(),
                verlag=fields["Verlag"].get().strip(),
                neupreis=preis,
                # ID aus der (ggf. neuen) Identität berechnen lassen — invariant.
                id="",
            )
            result["eintrag"] = new
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(8, 8))
        ttk.Button(btns, text="OK", command=on_ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Abbrechen", command=dlg.destroy).pack(side="left", padx=4)

        dlg.wait_window()
        return result["eintrag"]  # type: ignore[return-value]

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
