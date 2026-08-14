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
from core import catalog, config_io, gitops, paths
from gui import theme
from gui.widgets import Banner, BusyBar, CollapsibleSection, LogView, add_tooltip, confirm_action

# Fenster-Titel für filedialog (Windows-orientiert, spielt auf POSIX keine Rolle).
_EXCEL_FILETYPES = [("Excel-Dateien", "*.xlsx"), ("Alle Dateien", "*.*")]

# Treeview-Spalten (id wird als iid genutzt, nicht als Anzeigespalte).
_KAT_COLUMNS = ("fach", "hint", "von", "bis", "isbn", "titel", "verlag", "neupreis", "mjb")
_KAT_HEADERS = {
    "fach": "Fach",
    "hint": "Hinweis",
    "von": "Jg. von",
    "bis": "Jg. bis",
    "isbn": "Buchnummer",
    "titel": "Titel",
    "verlag": "Verlag",
    "neupreis": "Neupreis",
    "mjb": "Mehrere Jg.",
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
        # Kopf: Titel + Einordnung (statt Banner-als-erstes).
        header = ttk.Frame(self)
        header.pack(fill="x", padx=theme.SP_LG, pady=(theme.SP_LG, theme.SP_SM))
        ttk.Label(header, text="Bestandsliste", style=theme.HEADING_LABEL).pack(anchor="w")
        ttk.Label(
            header,
            text="Die jährliche Excel-Datei aus IServ aktualisieren und sehen, welche "
            "Bücher nachbestellt werden müssen.",
            style=theme.MUTED_LABEL,
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(theme.SP_XS, 0))

        # Hauptaktions-Karte: Prüfen (sicher) + Excel aktualisieren (daten-
        # verändernd, rot) + die zugehörige Excel-Auswahl — Kontrolle neben
        # dem, was sie beeinflusst.
        primary = ttk.LabelFrame(
            self, text="Jahresablauf", style=theme.CARD_FRAME
        )
        primary.pack(fill="x", padx=theme.SP_LG, pady=theme.SP_SM)
        prow = ttk.Frame(primary, style="Card.TFrame")
        prow.pack(fill="x", padx=theme.SP_MD, pady=theme.SP_MD)
        self._btn_dryrun = ttk.Button(
            prow,
            text="Erst prüfen (nichts ändern)",
            style=theme.PRIMARY_BUTTON,
            command=self.on_dry_run,
        )
        self._btn_dryrun.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_dryrun,
            "Liest IServ und zeigt einen Bericht. Die Excel-Datei bleibt unverändert.",
        )
        self._btn_real = ttk.Button(
            prow, text="Excel aktualisieren", style=theme.DANGER_BUTTON, command=self.on_real_run
        )
        self._btn_real.pack(side="left", padx=theme.SP_SM)
        add_tooltip(
            self._btn_real,
            "Überträgt die geprüften Zahlen in die Excel-Datei. Zuerst immer prüfen.",
        )

        excel_row = ttk.Frame(primary, style="Card.TFrame")
        excel_row.pack(fill="x", padx=theme.SP_MD, pady=(0, theme.SP_MD))
        ttk.Label(
            excel_row, text="Jahres-Excel:", style=theme.CARD_MUTED_LABEL, width=14, anchor="w"
        ).pack(side="left")
        self._excel_var = tk.StringVar(value="(keine ausgewählt)")
        ttk.Label(
            excel_row, textvariable=self._excel_var, style=theme.CARD_MUTED_LABEL, anchor="w"
        ).pack(side="left", fill="x", expand=True, padx=(0, theme.SP_SM))
        self._btn_pick = ttk.Button(
            excel_row, text="Datei auswählen …", command=self.on_pick_excel
        )
        self._btn_pick.pack(side="left")
        add_tooltip(self._btn_pick, "Wähle die Excel-Datei des aktuellen Schuljahres aus.")

        # Sekundäre Werkzeugleiste: seltene, einmalige Aktionen — bewusst
        # kleiner und abgesetzt, keine Peers der Jahres-Aktionen.
        secondary = ttk.Frame(self)
        secondary.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))
        ttk.Label(
            secondary, text="Einmalig / selten:", style=theme.MUTED_LABEL
        ).pack(side="left", padx=(0, theme.SP_SM))
        self._btn_install = ttk.Button(
            secondary, text="Einrichtung", style=theme.SECONDARY_BUTTON, command=self.on_install
        )
        self._btn_install.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_install,
            "Einmalig: richtet die jährliche Bestandsliste auf diesem Laptop ein.",
        )
        self._btn_update = ttk.Button(
            secondary, text="Aktualisieren", style=theme.SECONDARY_BUTTON, command=self.on_update
        )
        self._btn_update.pack(side="left")
        add_tooltip(self._btn_update, "Holt eine neue Version der Bestandslisten-Hilfe.")

        # Status-Banner + Busy-Bar.
        self._banner = Banner(self, "")
        self._banner.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))
        self._busy_bar = BusyBar(self)
        self._busy_bar.pack(fill="x", padx=theme.SP_LG)

        # Mittelteil: Katalog-Editor (oben, prominent), Erweitert (eingeklappt),
        # Report-Log (unten).
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=theme.SP_LG, pady=theme.SP_SM)

        # ── Katalog-Editor (Treeview + Aktionen in 3 Cluster gegliedert) ───
        kat = ttk.LabelFrame(
            mid, text="Buchkatalog (Fach und Jahrgang → Buchnummer)", style=theme.CARD_FRAME
        )
        kat.pack(fill="both", expand=True, pady=(0, theme.SP_SM))

        tree_row = ttk.Frame(kat, style="Card.TFrame")
        tree_row.pack(fill="both", expand=True, padx=theme.SP_SM, pady=(theme.SP_SM, theme.SP_XS))
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

        self._build_catalog_actions(kat)

        # ── Erweitert (eingeklappt): seltene, technische Sonderfälle. ──────
        # Raw-JSON-Sonder-Zuordnungen + Schuljahr-Override sind produktions-
        # wirksame Konfiguration (match_overrides) — bewusst nicht im
        # Hauptbereich, damit sie nicht "aus Versehen ohne Rücksprache"
        # geändert werden.
        adv = CollapsibleSection(mid, title="Erweitert (nur nach Rücksprache)")
        adv.pack(fill="x", pady=(0, theme.SP_SM))
        cfg = ttk.LabelFrame(
            adv.body, text="Zusätzliche Einstellungen", style=theme.CARD_FRAME
        )
        cfg.pack(fill="x", pady=(0, theme.SP_XS))
        ttk.Label(
            cfg,
            text="Diese Felder brauchst du im normalen Jahresablauf nicht. Bei Unsicherheit "
            "nichts ändern und die verantwortliche Person fragen.",
            style=theme.CARD_MUTED_LABEL,
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=theme.SP_SM, pady=(theme.SP_SM, 0))

        ss_row = ttk.Frame(cfg, style="Card.TFrame")
        ss_row.pack(fill="x", padx=theme.SP_SM, pady=(theme.SP_SM, theme.SP_XS))
        ttk.Label(
            ss_row, text="Reservebestand pro Buch:", style=theme.CARD_MUTED_LABEL,
            width=28, anchor="w",
        ).pack(side="left")
        self._safety_var = tk.StringVar()
        ttk.Entry(ss_row, textvariable=self._safety_var, width=8).pack(side="left")

        ov_row = ttk.Frame(cfg, style="Card.TFrame")
        ov_row.pack(fill="both", padx=theme.SP_SM, pady=theme.SP_XS)
        ttk.Label(
            ov_row,
            text="Sonder-Zuordnungen\n(nur nach Rücksprache):",
            style=theme.CARD_MUTED_LABEL,
            width=28,
            anchor="nw",
            justify="left",
        ).pack(side="left")
        self._overrides_text = tk.Text(
            ov_row, height=6, width=48, font=theme.MONO,
            background=theme.LOG_BG, foreground=theme.LOG_FG, relief="solid", borderwidth=1,
            padx=theme.SP_SM, pady=theme.SP_XS,
        )
        self._overrides_text.pack(side="left", fill="x", expand=True)

        cfg_btns = ttk.Frame(cfg, style="Card.TFrame")
        cfg_btns.pack(fill="x", padx=theme.SP_SM, pady=(theme.SP_XS, theme.SP_SM))
        self._btn_save_cfg = ttk.Button(
            cfg_btns,
            text="Zusätzliche Einstellungen speichern",
            command=self.on_save_config,
        )
        self._btn_save_cfg.pack(side="left")
        add_tooltip(
            self._btn_save_cfg,
            "Nur verwenden, wenn die verantwortliche Person eine Sonderänderung vorgibt.",
        )
        self._btn_reload_cfg = ttk.Button(
            cfg_btns,
            text="Neu laden",
            style=theme.SECONDARY_BUTTON,
            command=self._load_config_into_form,
        )
        self._btn_reload_cfg.pack(side="left", padx=theme.SP_SM)
        add_tooltip(
            self._btn_reload_cfg,
            "Lädt die zuletzt gespeicherten zusätzlichen Einstellungen.",
        )

        # Schuljahr (optional, frei gelassen = aktuelles) — ebenfalls "Erweitert".
        sy_row = ttk.Frame(adv.body)
        sy_row.pack(fill="x", pady=(0, theme.SP_XS))
        ttk.Label(
            sy_row, text="Schuljahr (nur falls nötig):", width=28, anchor="w"
        ).pack(side="left")
        self._schoolyear_var = tk.StringVar()
        ttk.Entry(sy_row, textvariable=self._schoolyear_var, width=14).pack(side="left")
        ttk.Label(
            sy_row, text='z. B. "2025/2026"; leer = aktuelles', style=theme.MUTED_LABEL
        ).pack(side="left", padx=theme.SP_SM)

        # Report-Log (unten, füllt den Rest).
        self._log = LogView(mid, height=14)
        self._log.pack(fill="both", expand=True)
        self._log.append(
            "Bereit. „Einrichtung“ nur bei der ersten Nutzung klicken. Danach "
            "Jahres-Excel auswählen und immer zuerst „Erst prüfen“ verwenden."
        )
        self._log.append(
            "Die Prüfung ändert nichts. „Excel aktualisieren“ erst nach einem "
            "plausiblen Prüfbericht klicken; die alte Excel wird vorher gesichert."
        )

    def _build_catalog_actions(self, kat: ttk.Widget) -> None:
        """Gliedert die acht Katalog-Aktionen in drei beschriftete Cluster.

        Der Katalog bleibt sichtbar (prominent), aber die bisher flachen
        acht Peer-Knöpfe werden gruppiert: Daten (Import/Erzeugen/Übernehmen),
        Einträge (Hinzufügen/Bearbeiten/Entfernen), Katalog (Speichern/Neu
        laden). Alle sekundär gestylt — keine ist die Jahres-Hauptaktion.
        """
        bar = ttk.Frame(kat, style="Card.TFrame")
        bar.pack(fill="x", padx=theme.SP_SM, pady=(theme.SP_XS, theme.SP_SM))
        for c in (0, 2, 4):
            bar.columnconfigure(c, weight=1, uniform="c")

        clusters: tuple[tuple[str, tuple[tuple[str, object, str], ...]], ...] = (
            (
                "Daten",
                (
                    ("Bücher aus Excel übernehmen", self.on_katalog_import,
                     "Übernimmt die Fach-, Jahrgangs- und Buchdaten aus einer vorhandenen Excel."),
                    ("Neue Excel aus Katalog", self.on_katalog_render,
                     "Erstellt eine neue Excel-Datei aus der Vorlage und dem Katalog."),
                    ("Zuordnungen übernehmen", self.on_katalog_sync,
                     "Übernimmt die Katalog-Zuordnungen für die Bestandsprüfung."),
                ),
            ),
            (
                "Einträge",
                (
                    ("Hinzufügen", self.on_katalog_add,
                     "Legt eine neue Buch-Zuordnung (Fach, Jahrgang, Buchnummer) an."),
                    ("Bearbeiten", self.on_katalog_edit,
                     "Bearbeitet die ausgewählte Buch-Zuordnung (auch per Doppelklick)."),
                    ("Entfernen", self.on_katalog_remove,
                     "Entfernt die ausgewählte Buch-Zuordnung (erst dauerhaft nach „Speichern“)."),
                ),
            ),
            (
                "Katalog",
                (
                    ("Speichern", self.on_katalog_save,
                     "Schreibt den bearbeiteten Katalog dauerhaft in die Katalog-Datei."),
                    ("Verwerfen / neu laden", self.on_katalog_reload,
                     "Verwirft nicht gespeicherte Änderungen und lädt den Katalog neu."),
                ),
            ),
        )
        for ci, (caption, btns) in enumerate(clusters):
            col = ci * 2
            cell = ttk.Frame(bar, style="Card.TFrame")
            cell.grid(row=0, column=col, sticky="ew", padx=(theme.SP_SM if ci else 0, 0))
            ttk.Label(
                cell, text=caption, style=theme.CARD_MUTED_LABEL
            ).pack(anchor="w")
            row = ttk.Frame(cell, style="Card.TFrame")
            row.pack(fill="x", pady=(theme.SP_XS, 0))
            for text, cmd, tip in btns:
                b = ttk.Button(row, text=text, style=theme.SECONDARY_BUTTON, command=cmd)
                b.pack(side="left", padx=(0, theme.SP_XS))
                add_tooltip(b, tip)
            if ci < 2:
                ttk.Separator(bar, orient="vertical").grid(
                    row=0, column=col + 1, sticky="ns", padx=theme.SP_SM
                )

    # --- Config laden/speichern --------------------------------------------

    def _load_config_into_form(self) -> None:
        """Liest ``config.json`` (Defaults bei Fehlen) ins Formular."""
        try:
            cfg = config_io.read_editable()
        except Exception as e:  # noqa: BLE001 — kaputte JSON soll GUI nicht crashen
            self._log.append(f"Zusätzliche Einstellungen konnten nicht gelesen werden: {e}")
            return
        self._safety_var.set(str(cfg.safety_stock))
        self._overrides_text.delete("1.0", "end")
        self._overrides_text.insert("1.0", config_io.format_match_overrides(cfg.match_overrides))

    def on_save_config(self) -> None:
        """Validiert + speichert safety_stock + match_overrides (erhält Rest)."""
        try:
            safety = int(self._safety_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Eingabe prüfen", "Der Reservebestand muss eine ganze Zahl sein."
            )
            return
        try:
            overrides = config_io.parse_match_overrides_text(
                self._overrides_text.get("1.0", "end")
            )
        except config_io.ConfigError as e:
            messagebox.showerror("Eingabe prüfen", str(e))
            return
        try:
            config_io.write_editable(safety, overrides)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                "Speichern",
                f"Die Einstellungen konnten nicht gespeichert werden: {e}",
            )
            return
        self._log.append("Zusätzliche Einstellungen gespeichert.", kind="success")

    # --- Katalog-Editor -----------------------------------------------------

    def _load_katalog(self) -> None:
        """Lädt ``data/katalog.json`` (leer bei Fehlen) und befüllt den Treeview."""
        try:
            self._katalog = catalog.load_katalog()
        except Exception as e:  # noqa: BLE001 — kaputte JSON soll GUI nicht crashen
            self._log.append(f"Buchkatalog konnte nicht gelesen werden: {e}")
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
        self._log.append("Buchkatalog neu geladen. Nicht gespeicherte Änderungen sind verworfen.")

    def on_katalog_save(self) -> None:
        """Schreibt den In-Memory-Katalog nach ``data/katalog.json``."""
        try:
            catalog.save_katalog(self._katalog)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                "Katalog speichern",
                f"Der Buchkatalog konnte nicht gespeichert werden: {e}",
            )
            return
        self._log.append(
            f"Buchkatalog gespeichert ({len(self._katalog.eintraege)} Einträge).", kind="success"
        )

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
                log(f"Buchdaten übernommen: {len(kat.eintraege)} Einträge.")
            except Exception as e:  # noqa: BLE001
                log(f"Buchdaten konnten nicht übernommen werden: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_katalog_render(self) -> None:
        """Erzeugt eine Excel-Datei aus der mitgelieferten Vorlage."""
        template = paths.templates_dir() / "Bestand-Vorlage.xlsx"
        if not template.is_file():
            messagebox.showerror(
                "Vorlage fehlt",
                "Die mitgelieferte Excel-Vorlage wurde nicht gefunden. "
                "Bitte die Einrichtung prüfen.",
            )
            return
        out = filedialog.asksaveasfilename(
            title="Neue Jahres-Excel speichern unter",
            defaultextension=".xlsx",
            filetypes=_EXCEL_FILETYPES,
        )
        if not out:
            return

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                _, unmatched = catalog.render_excel(
                    Path(template), self._katalog, Path(out)
                )
                log(f"Neue Excel-Datei erstellt: {out}")
                if unmatched:
                    log(f"{len(unmatched)} Buch-Zuordnung(en) konnten nicht eingeordnet werden:")
                    for u in unmatched:
                        log(f"    - {u}")
                else:
                    log("Alle Buch-Zuordnungen wurden übernommen.")
            except Exception as e:  # noqa: BLE001
                log(f"Neue Excel-Datei konnte nicht erstellt werden: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_katalog_sync(self) -> None:
        """Schreibt ``match_overrides`` aus dem Katalog in die config.json."""
        try:
            overrides = catalog.catalog_to_overrides(self._katalog)
            safety = config_io.read_config().safety_stock
            config_io.write_editable(safety, overrides)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(
                "Zuordnungen übernehmen",
                f"Die Zuordnungen konnten nicht übernommen werden: {e}",
            )
            return
        self._load_config_into_form()
        self._log.append(
            f"{len(overrides)} Buch-Zuordnungen übernommen."
        )

    def on_katalog_add(self) -> None:
        eintrag = self._edit_dialog()
        if eintrag is None:
            return
        self._katalog.eintraege.append(eintrag)
        self._populate_tree()
        self._log.append(
            f"Buch-Zuordnung hinzugefügt: {eintrag.fach} "
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
            f"Buch-Zuordnung bearbeitet: {updated.fach} "
            f"Jg.{updated.jahrgang_von}-{updated.jahrgang_bis}"
        )

    def on_katalog_remove(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        eid = sel[0]
        eintrag = next((e for e in self._katalog.eintraege if e.id == eid), None)
        label = (
            f"{eintrag.fach} Jg.{eintrag.jahrgang_von}-{eintrag.jahrgang_bis}"
            if eintrag
            else eid
        )
        if not confirm_action(
            self,
            "Buch-Zuordnung entfernen?",
            f"„{label}“ wird aus dem Katalog entfernt (erst dauerhaft nach "
            "„Katalog speichern“).",
        ):
            return
        self._katalog.eintraege = [e for e in self._katalog.eintraege if e.id != eid]
        self._populate_tree()
        self._log.append(
            "Buch-Zuordnung entfernt. Danach „Katalog speichern“ klicken.", kind="warning"
        )

    def _edit_dialog(self, eintrag: catalog.Eintrag | None = None) -> catalog.Eintrag | None:
        """Modal-Dialog zum Anlegen/Bearbeiten eines Eintrags; None bei Abbruch."""
        dlg = tk.Toplevel(self)
        dlg.title("Buch-Zuordnung bearbeiten" if eintrag else "Buch-Zuordnung hinzufügen")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(True, True)

        fields: dict[str, tk.StringVar] = {}
        e = eintrag or catalog.Eintrag(fach="", jahrgang_von=5, jahrgang_bis=5, isbn="")
        defaults = {
            "Fach": e.fach,
            "Hinweis": e.hint or "",
            "Jahrgang von": str(e.jahrgang_von),
            "Jahrgang bis": str(e.jahrgang_bis),
            "Buchnummer (ISBN)": e.isbn,
            "Titel": e.titel,
            "Verlag": e.verlag,
            "Neupreis": f"{e.neupreis:.2f}" if e.neupreis else "",
        }
        _keys = [
            "Fach",
            "Hinweis",
            "Jahrgang von",
            "Jahrgang bis",
            "Buchnummer (ISBN)",
            "Titel",
            "Verlag",
            "Neupreis",
        ]
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
                von = int(fields["Jahrgang von"].get().strip())
                bis = int(fields["Jahrgang bis"].get().strip())
            except ValueError:
                messagebox.showerror(
                    "Eingabe prüfen",
                    "Die beiden Jahrgangsfelder müssen ganze Zahlen sein.",
                    parent=dlg,
                )
                return
            try:
                preis = float(fields["Neupreis"].get().strip() or "0")
            except ValueError:
                messagebox.showerror(
                    "Eingabe prüfen", "Der Neupreis muss eine Zahl sein.", parent=dlg
                )
                return
            hint = fields["Hinweis"].get().strip() or None
            new = catalog.Eintrag(
                fach=fields["Fach"].get().strip(),
                jahrgang_von=von,
                jahrgang_bis=bis,
                isbn=fields["Buchnummer (ISBN)"].get().strip(),
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
        ttk.Button(btns, text="Übernehmen", command=on_ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Abbrechen", command=dlg.destroy).pack(side="left", padx=4)

        dlg.wait_window()
        return result["eintrag"]  # type: ignore[return-value]

    # --- Excel-Auswahl -----------------------------------------------------

    def on_pick_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Jahres-Excel auswählen", filetypes=_EXCEL_FILETYPES
        )
        if path:
            self._excel_path = Path(path)
            self._excel_var.set(str(self._excel_path))

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Einrichtung", bst.install)

    def on_update(self) -> None:
        self._run_async("Aktualisierung", bst.update)

    def on_dry_run(self) -> None:
        self._run_run(dry_run=True)

    def on_real_run(self) -> None:
        ok = confirm_action(
            self,
            "Excel aktualisieren?",
            "Die ausgewählte Excel-Datei wird mit den neuen Zahlen überschrieben. "
            "Die bisherige Datei wird vorher als Sicherungskopie abgelegt.\n\n"
            "Hast du den Prüfbericht angesehen und sind die Zahlen plausibel?",
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
            messagebox.showinfo("Jahres-Excel", "Bitte zuerst eine Jahres-Excel auswählen.")
            return
        schoolyear = self._schoolyear_var.get().strip() or None
        label = "Prüfung" if dry_run else "Excel aktualisieren"

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                rc = bst.run_auto(
                    dry_run=dry_run, excel=excel, schoolyear=schoolyear, log=log
                )
                tag = "Prüfung" if dry_run else "Excel-Aktualisierung"
                if rc == 0:
                    self.after(0, lambda: self._log.append(f"{tag} abgeschlossen.", kind="success"))
                else:
                    self.after(
                        0,
                        lambda: self._log.append(
                            f"{tag} beendet. Bitte den Bericht und die Fehlermeldung prüfen.",
                            kind="error",
                        ),
                    )
                    self.after(
                        0,
                        lambda: self._banner.set_text(
                            f"{tag} beendet — Bericht prüfen. Bei Unklarheit: "
                            "USB-Handscanner und offizielles IServ-Frontend nutzen.",
                            "error",
                        ),
                    )
            except Exception as e:  # noqa: BLE001
                msg = f"{label} nicht abgeschlossen: {e}"
                self.after(0, lambda: self._log.append(msg, kind="error"))
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
                self.after(0, lambda: self._log.append(f"{label} abgeschlossen.", kind="success"))
            except Exception as e:  # noqa: BLE001
                msg = f"{label} nicht abgeschlossen: {e}"
                self.after(0, lambda: self._log.append(msg, kind="error"))
            finally:
                self.after(0, self._end_busy)

        self._begin_busy(label)
        threading.Thread(target=worker, daemon=True).start()

    # --- Busy-Status -------------------------------------------------------

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_dryrun, self._btn_real):
            b.state(["disabled"])
        self._busy_bar.start(f"{label} läuft …")
        self._banner.set_text(f"{label} läuft …", "warning")

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update, self._btn_dryrun, self._btn_real):
            b.state(["!disabled"])
        self._busy_bar.stop()
        self._refresh_status()

    # --- Status ------------------------------------------------------------

    def _refresh_status(self) -> None:
        """Zeigt verständlich, ob die Bestandsliste eingerichtet ist."""
        st = gitops.status("ausleihe-api")
        ready = bst.bestand_venv_python().is_file()
        if not st.installed:
            self._banner.set_text(
                "Noch nicht eingerichtet. Zuerst „Einrichtung“ klicken.", "warning"
            )
        elif not ready:
            self._banner.set_text("Bestandsliste wird noch vorbereitet.", "warning")
        else:
            self._banner.set_text(
                "Bereit. Jahres-Excel auswählen und immer zuerst „Erst prüfen“ verwenden.",
                "success",
            )


def build(parent: tk.Widget) -> BestandTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return BestandTab(parent)
