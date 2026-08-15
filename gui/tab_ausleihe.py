"""Tab: ausleihe-ausgabe (dünn — alle Logik in ``core.ausleihe_ausgabe``).

Aktionen: Installieren, Updaten, Server starten/stopen, Host öffnen, plus
die zentrale ``.env``-Form (IServ-Zugang + Host-Passwort), die in **beide**
Geschwister-``.env`` schreibt.

Phase 8 — Layout-Neubau für Nicht-Techniker (Apple-Design-Prinzipien,
Tkinter-übersetzt): statt einer flachen Kette aus Knöpfen + Banner + Log +
Form gibt es eine klare vertikale Hierarchie — *Bereitschaft zuerst, dann die
eine tägliche Aktion, dann Verwaltung, dann Protokoll*:

1. **Status-Leiste** (``StatusBar``) — primäre Rückmeldung: Zustand + nächste
   Aktion auf einen Blick (§16 Wayfinding).
2. **Tägliche Bedienung** — ein *zustandsabhängiger* Haupt-Knopf: läuft nichts
   → „Ausleihe starten” (blau); läuft die Ausleihe → „Ausleihe beenden” (rot,
   an gleicher Stelle). Eine offensichtliche Aktion pro Bildschirm, immer die
   richtige (§6 Einfachheit).
3. **Verwaltung** (eingeklappt, ``CollapsibleSection``) — Einrichtung/
   Aktualisieren + Zugangsdaten-Form. Bewusst sekundär: ehrlich beschriftet,
   nicht versteckt (§6: common path first, advanced one level deeper).
4. **Protokoll** (``Eyebrow`` + ``LogView``, reduziert) — für die Fehlersuche,
   nicht der erste Anblick.

Lange Operationen (install/update) laufen in einem Hintergrund-Thread; deren
``log``-Callback hängt Zeilen thread-safe via ``after(0, …)`` ins LogView. Der
dauerhafte Server streamt selbst über den :class:`~core.process.SubprocessManager`.

Produktionsschutz: die Form speichert nur in ``.env`` — kein Schreiben ans
IServ, kein Umschalten von ``ALLOW_BOOKING``. ``.env``-Speichern ist
gesperrt, solange die Repos noch nicht geklont sind.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from core import ausleihe_ausgabe as aa
from core import envtool, gitops, paths
from core.process import SubprocessManager
from gui import theme
from gui.widgets import (
    BusyBar,
    CollapsibleSection,
    Eyebrow,
    FormField,
    LogView,
    StatusBar,
    add_tooltip,
    run_async,
)

# Form-Felder: (key, label, masked). Einzige Quelle: core.envtool.FORM_FIELDS
# (teilt sich mit dem Ersteinrichtungs-Assistenten ``gui/setup_wizard.py``).
_ENV_FIELDS: tuple[tuple[str, str, bool], ...] = envtool.FORM_FIELDS


class AusleiheTab(ttk.Frame):
    """Tab-Oberfläche für das ausleihe-ausgabe-Werkzeug."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._manager = SubprocessManager()
        self._busy = False
        self._build()
        self._load_form_into_fields()
        self._refresh_status()
        # Poll-Schleife für den Server-Stream (läuft selbst weiter).
        self._log.poll(self._manager)

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        # Kopf: Titel + Einordnung.
        header = ttk.Frame(self)
        header.pack(fill="x", padx=theme.SP_LG, pady=(theme.SP_LG, theme.SP_SM))
        ttk.Label(header, text="Ausleihe & Ausgabe", style=theme.HEADING_LABEL).pack(anchor="w")
        ttk.Label(
            header,
            text="Bücherstapel für eine Klasse bearbeiten. Täglicher Ablauf: starten, "
            "Arbeitsfenster öffnen, nach dem Einsatz beenden.",
            style=theme.MUTED_LABEL,
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(theme.SP_XS, 0))

        # Status-Leiste: primäre Rückmeldung — Zustand + nächste Aktion.
        self._status = StatusBar(self)
        self._status.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))

        # Busy-Bar (nur während langer Aktionen sichtbar).
        self._busy_bar = BusyBar(self)
        self._busy_bar.pack(fill="x", padx=theme.SP_LG)

        # Tägliche Bedienung: der eine, zustandsabhängige Haupt-Knopf + Öffnen.
        primary = ttk.LabelFrame(self, text="Tägliche Bedienung", style=theme.CARD_FRAME)
        primary.pack(fill="x", padx=theme.SP_LG, pady=theme.SP_SM)
        prow = ttk.Frame(primary, style="Card.TFrame")
        prow.pack(fill="x", padx=theme.SP_MD, pady=theme.SP_MD)
        self._btn_primary = ttk.Button(
            prow, text="Ausleihe starten", style=theme.PRIMARY_BUTTON, command=self.on_start
        )
        self._btn_primary.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_primary,
            "Startet den Dienst auf diesem Laptop. Danach das Arbeitsfenster öffnen.",
        )
        self._btn_open = ttk.Button(
            prow, text="Arbeitsfenster öffnen", command=self.on_open_host
        )
        self._btn_open.pack(side="left", padx=theme.SP_SM)
        add_tooltip(
            self._btn_open,
            "Öffnet die Seite, auf der du Schuljahr, Klasse und Helfer auswählst.",
        )

        # Verwaltung: seltene / einmalige Aktionen + Zugangsdaten — eingeklappt,
        # sobald die Ausleihe bereit ist (§6: advanced one level deeper).
        self._verwaltung = CollapsibleSection(
            self, title="Verwaltung · nur bei der Einrichtung / selten", expanded=False
        )
        self._verwaltung.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))
        self._build_verwaltung(self._verwaltung.body)

        # Protokoll: bewusst sekundär — für die Fehlersuche, nicht der Alltag.
        log_row = ttk.Frame(self)
        log_row.pack(fill="both", expand=True, padx=theme.SP_LG, pady=(0, theme.SP_LG))
        Eyebrow(log_row, text="Protokoll · für die Fehlersuche").pack(
            anchor="w", pady=(0, theme.SP_XS)
        )
        self._log = LogView(log_row, height=8)
        self._log.pack(fill="both", expand=True)
        self._log.append(
            "Bereit. Bei der ersten Nutzung „Einrichtung” klicken (in der Verwaltung "
            "oder über die Status-Leiste), danach Zugangsdaten eintragen und speichern."
        )
        self._log.append(
            "Beim Öffnen kann eine Zertifikat-Warnung erscheinen. Im lokalen "
            "Schul-WLAN ist das erwartet; die Hilfe erklärt den nächsten Klick."
        )

    def _build_verwaltung(self, parent: tk.Widget) -> None:
        """Einrichtung/Aktualisieren + Zugangsdaten-Form im eingeklappten Bereich."""
        # Seltene Aktionen.
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, theme.SP_XS))
        self._btn_install = ttk.Button(
            actions, text="Einrichtung", style=theme.SECONDARY_BUTTON, command=self.on_install
        )
        self._btn_install.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_install,
            "Einmalig: lädt die benötigten Teile herunter und bereitet die Ausleihe vor.",
        )
        self._btn_update = ttk.Button(
            actions, text="Aktualisieren", style=theme.SECONDARY_BUTTON, command=self.on_update
        )
        self._btn_update.pack(side="left")
        add_tooltip(
            self._btn_update,
            "Holt eine neue Version. Nur verwenden, wenn eine Aktualisierung nötig ist.",
        )
        ttk.Label(
            parent, text="Einmalig / selten — im Alltag nicht nötig.", style=theme.MUTED_LABEL
        ).pack(anchor="w", pady=(0, theme.SP_MD))

        # Zugangsdaten (nur bei der Einrichtung).
        form = ttk.LabelFrame(parent, text="Zugangsdaten", style=theme.CARD_FRAME)
        form.pack(fill="x")
        self._fields: dict[str, FormField] = {}
        for key, label, masked in _ENV_FIELDS:
            f = FormField(form, label=label, masked=masked)
            f.pack(fill="x", padx=theme.SP_MD, pady=theme.SP_XS)
            self._fields[key] = f
        ttk.Label(
            form,
            text="Die Angaben bleiben auf diesem Laptop. Passwörter werden nicht im "
            "Protokoll angezeigt.",
            style=theme.CARD_MUTED_LABEL,
            wraplength=820,
            justify="left",
        ).pack(anchor="w", padx=theme.SP_MD, pady=(theme.SP_SM, theme.SP_XS))
        ttk.Button(
            form,
            text="Zugangsdaten speichern",
            style=theme.SECONDARY_BUTTON,
            command=self.on_save_env,
        ).pack(anchor="w", padx=theme.SP_MD, pady=(theme.SP_XS, theme.SP_MD))

    # --- .env-Form --------------------------------------------------------

    def _load_form_into_fields(self) -> None:
        """Lädt Werte aus vorhandenen ``.env`` + leere aus ``.env.example``."""
        values = envtool.read_form()
        for key, f in self._fields.items():
            val = values.get(key, "")
            if not val:
                # Default aus .env.example (z. B. ISERV_DOMAIN), falls Repo da.
                for repo in ("ausleihe-ausgabe", "ausleihe-api"):
                    if paths.exists(repo):
                        val = envtool.defaults_from_example(repo).get(key, "")
                        if val:
                            break
            f.set(val)

    def on_save_env(self) -> None:
        """Schreibt die Form in **beide** ``.env`` — nur wenn Repos geklont."""
        if not (paths.exists("ausleihe-ausgabe") and paths.exists("ausleihe-api")):
            self._log.append(
                "Die Einrichtung ist noch nicht fertig. Bitte zuerst „Einrichtung” "
                "klicken; die eingetragenen Werte bleiben im Formular."
            )
            return
        values = {key: f.get() for key, f in self._fields.items()}
        envtool.write_form(values)
        self._log.append(
            "Zugangsdaten gespeichert. Die Ausleihe kann jetzt gestartet werden.", kind="success"
        )
        self._refresh_status()

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        if self._busy:
            return
        run_async(
            self, "Einrichtung", aa.install,
            log=self._log, status=self._status, busy_bar=self._busy_bar,
            buttons=(self._btn_install, self._btn_update, self._btn_primary, self._btn_open),
            set_busy=lambda b: setattr(self, "_busy", b),
            on_done=self._after_manage_done,
        )

    def on_update(self) -> None:
        if self._busy:
            return
        run_async(
            self, "Aktualisierung", aa.update,
            log=self._log, status=self._status, busy_bar=self._busy_bar,
            buttons=(self._btn_install, self._btn_update, self._btn_primary, self._btn_open),
            set_busy=lambda b: setattr(self, "_busy", b),
            on_done=self._after_manage_done,
        )

    def _after_manage_done(self) -> None:
        """Nach Einrichtung/Aktualisierung: Repos können neu da sein → Form
        neu laden, danach Status neu setzen (wie zuvor in ``_end_busy``)."""
        self._load_form_into_fields()
        self._refresh_status()

    def on_start(self) -> None:
        try:
            aa.start_server(self._manager)
            self._log.append(
                "Ausleihe gestartet. Jetzt „Arbeitsfenster öffnen” klicken.", kind="success"
            )
        except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt
            self._log.append(f"Ausleihe konnte nicht gestartet werden: {e}", kind="error")
            self._status.set(
                "error",
                "Start fehlgeschlagen",
                "Wenn das nicht klappt: USB-Handscanner und offizielles "
                "IServ-Ausleihe-Frontend verwenden.",
            )
            return  # Fehlerstatus stehen lassen — kein Refresh überschreibt ihn.
        self._refresh_status()

    def on_stop(self) -> None:
        if not self._manager.is_running():
            self._log.append("Die Ausleihe läuft gerade nicht.")
            return
        if self._busy:
            return
        # aa.stop_server()/manager.stop() kann bis zu ~10s blockieren (zwei
        # sequenzielle 5s-proc.wait-Timeouts) — daher im Hintergrund-Thread,
        # sonst friert das Fenster für die Dauer spürbar ein.
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_primary, self._btn_open):
            b.state(["disabled"])
        self._busy_bar.start("Ausleihe wird beendet …")

        def worker() -> None:
            aa.stop_server(self._manager)
            self.after(0, self._on_stop_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop_done(self) -> None:
        if not self.winfo_exists():
            return
        self._busy = False
        for b in (self._btn_install, self._btn_update):
            b.state(["!disabled"])
        self._busy_bar.stop()
        self._log.append("Ausleihe beendet.", kind="success")
        self._refresh_status()

    def on_open_host(self) -> None:
        try:
            url = aa.open_host()
            self._log.append(f"Arbeitsfenster geöffnet: {url}", kind="success")
        except Exception as e:  # noqa: BLE001
            self._log.append(f"Arbeitsfenster konnte nicht geöffnet werden: {e}", kind="error")

    # --- Status ------------------------------------------------------------

    def is_running(self) -> bool:
        """Für das Start-Dashboard (``gui/tab_home.py``): läuft der Server?"""
        return self._manager.is_running()

    def _refresh_status(self) -> None:
        """Setzt Status-Leiste + zustandsabhängigen Haupt-Knopf neu.

        Vier Zustände: läuft → Beenden (rot); bereit (eingerichtet + Zugangs-
        daten) → Starten (blau); fast bereit (eingerichtet, Zugangsdaten fehlen)
        → Verwaltung öffnen; nicht eingerichtet → Einrichtung starten.
        """
        installed = all(gitops.status(name).installed for name in aa.AUSLEIHE_REPOS)
        env_ready = envtool.is_ready("ausleihe-ausgabe")
        running = self._manager.is_running()
        if running:
            self._btn_primary.configure(
                text="Ausleihe beenden", style=theme.DANGER_BUTTON, command=self.on_stop
            )
            self._btn_primary.state(["!disabled"])
            self._btn_open.state(["!disabled"])
            self._status.set(
                "success",
                "Ausleihe läuft",
                "Nicht vergessen, nach dem Einsatz „Ausleihe beenden” zu klicken.",
                action_text="Ausleihe beenden",
                action_cmd=self.on_stop,
                action_style=theme.DANGER_BUTTON,
            )
        elif installed and env_ready:
            self._btn_primary.configure(
                text="Ausleihe starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["!disabled"])
            self._btn_open.state(["disabled"])
            self._status.set(
                "info",
                "Bereit",
                "Auf „Ausleihe starten” klicken, danach das Arbeitsfenster öffnen.",
            )
        elif installed:
            self._btn_primary.configure(
                text="Ausleihe starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["disabled"])
            self._btn_open.state(["disabled"])
            self._status.set(
                "warning",
                "Fast bereit",
                "Zugangsdaten fehlen — unten „Verwaltung” ausklappen, eintragen und speichern.",
                action_text="Verwaltung öffnen",
                action_cmd=self._verwaltung.expand,
                action_style=theme.SECONDARY_BUTTON,
            )
        else:
            self._btn_primary.configure(
                text="Ausleihe starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["disabled"])
            self._btn_open.state(["disabled"])
            self._status.set(
                "warning",
                "Noch nicht eingerichtet",
                "Einrichtung lädt die nötigen Teile (einmalig, kann einige Minuten dauern).",
                action_text="Einrichtung starten",
                action_cmd=self.on_install,
                action_style=theme.SECONDARY_BUTTON,
            )


def build(parent: tk.Widget) -> AusleiheTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return AusleiheTab(parent)
