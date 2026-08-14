"""Tab: ausleihe-ausgabe (dünn — alle Logik in ``core.ausleihe_ausgabe``).

Aktionen: Installieren, Updaten, Server starten/stopen, Host öffnen, plus
die zentrale ``.env``-Form (IServ-Zugang + Host-Passwort), die in **beide**
Geschwister-``.env`` schreibt.

Phase 7 — Zonen-Neubau: Kopf (Titel + Einordnung) → Hauptaktions-Karte
(tägliche Start/Öffnen/Beenden-Knöpfe) → sekundäre Werkzeugleiste (seltene
Einrichtung/Aktualisieren, bewusst kleiner und abgesetzt) → Status-Banner →
Log → Zugangsdaten-Karte. Lange Operationen (install/update) laufen in einem
Hintergrund-Thread; deren ``log``-Callback hängt Zeilen thread-safe via
``after(0, …)`` ins LogView. Der dauerhafte Server streamt selbst über den
:class:`~core.process.SubprocessManager` (eigener Thread + Queue).

Produktionsschutz: die Form speichert nur in ``.env`` — kein Schreiben ans
IServ, kein Umschalten von ``ALLOW_BOOKING``. ``.env``-Speichern ist
gesperrt, solange die Repos noch nicht geklont sind (sonst entstünde ein
leeres Repo-Verzeichnis, das clone später blockieren würde).
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from core import ausleihe_ausgabe as aa
from core import envtool, gitops, paths
from core.process import SubprocessManager
from gui import theme
from gui.widgets import Banner, BusyBar, FormField, LogView, add_tooltip

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
        # Poll-Schleife für den Server-Stream starten (läuft selbst weiter).
        self._log.poll(self._manager)

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        # Kopf: Titel + Einordnung (statt Banner-als-erstes).
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

        # Hauptaktions-Karte: die täglichen Knöpfe, groß und hervorgehoben.
        primary = ttk.LabelFrame(
            self, text="Tägliche Bedienung", style=theme.CARD_FRAME
        )
        primary.pack(fill="x", padx=theme.SP_LG, pady=theme.SP_SM)
        prow = ttk.Frame(primary, style="Card.TFrame")
        prow.pack(fill="x", padx=theme.SP_MD, pady=theme.SP_MD)
        self._btn_start = ttk.Button(
            prow, text="Ausleihe starten", style=theme.PRIMARY_BUTTON, command=self.on_start
        )
        self._btn_start.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_start,
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
        self._btn_stop = ttk.Button(
            prow, text="Ausleihe beenden", command=self.on_stop
        )
        self._btn_stop.pack(side="left", padx=theme.SP_SM)
        add_tooltip(self._btn_stop, "Beendet die Ausleihe nach dem Einsatz.")

        # Sekundäre Werkzeugleiste: seltene, einmalige Aktionen — bewusst
        # kleiner und abgesetzt, keine Peers der täglichen Knöpfe.
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
            "Einmalig: lädt die benötigten Teile herunter und bereitet die Ausleihe vor.",
        )
        self._btn_update = ttk.Button(
            secondary, text="Aktualisieren", style=theme.SECONDARY_BUTTON, command=self.on_update
        )
        self._btn_update.pack(side="left")
        add_tooltip(
            self._btn_update,
            "Holt eine neue Version. Nur verwenden, wenn eine Aktualisierung nötig ist.",
        )

        # Status-Banner.
        self._banner = Banner(self, "")
        self._banner.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))

        self._busy_bar = BusyBar(self)
        self._busy_bar.pack(fill="x", padx=theme.SP_LG)

        # Log (Arbeitsfenster).
        self._log = LogView(self, height=12)
        self._log.pack(fill="both", expand=True, padx=theme.SP_LG, pady=theme.SP_SM)
        self._log.append(
            "Bereit. Bei der ersten Nutzung „Einrichtung“ klicken, danach "
            "Zugangsdaten eintragen und speichern."
        )
        self._log.append(
            "Beim Öffnen kann eine Zertifikat-Warnung erscheinen. Im lokalen "
            "Schul-WLAN ist das erwartet; die Hilfe erklärt den nächsten Klick."
        )

        # Zugangsdaten-Karte (unten).
        form = ttk.LabelFrame(
            self, text="Zugangsdaten (nur bei der Einrichtung)", style=theme.CARD_FRAME
        )
        form.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_LG))
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
            wraplength=860,
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
                "Die Einrichtung ist noch nicht fertig. Bitte zuerst „Einrichtung“ "
                "klicken; die eingetragenen Werte bleiben im Formular."
            )
            return
        values = {key: f.get() for key, f in self._fields.items()}
        envtool.write_form(values)
        self._log.append(
            "Zugangsdaten gespeichert. Die Ausleihe kann jetzt gestartet werden.",
            kind="success",
        )

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Einrichtung", aa.install)

    def on_update(self) -> None:
        self._run_async("Aktualisierung", aa.update)

    def on_start(self) -> None:
        try:
            aa.start_server(self._manager)
            self._log.append(
                "Ausleihe gestartet. Jetzt „Arbeitsfenster öffnen“ klicken.", kind="success"
            )
        except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt
            self._log.append(f"Ausleihe konnte nicht gestartet werden: {e}", kind="error")
            self._banner.set_text(
                "Start fehlgeschlagen. Wenn das nicht klappt: USB-Handscanner und "
                "offizielles IServ-Ausleihe-Frontend verwenden.",
                "error",
            )
        self._refresh_status()

    def on_stop(self) -> None:
        if not self._manager.is_running():
            self._log.append("Die Ausleihe läuft gerade nicht.")
            return
        aa.stop_server(self._manager)
        self._log.append("Ausleihe beendet.", kind="success")
        self._refresh_status()

    def on_open_host(self) -> None:
        try:
            url = aa.open_host()
            self._log.append(f"Arbeitsfenster geöffnet: {url}", kind="success")
        except Exception as e:  # noqa: BLE001
            self._log.append(f"Arbeitsfenster konnte nicht geöffnet werden: {e}", kind="error")

    # --- Async-Hilfen ------------------------------------------------------

    def _run_async(self, label: str, fn) -> None:
        """Führt ``fn(log)`` in einem Hintergrund-Thread; loggt ins LogView.

        ``fn`` ist eine core-Funktion mit Signatur ``(log: LogFn) -> None``.
        Während des Laufs sind die Aktions-Buttons deaktiviert. Exceptions
        werden ins Log geschrieben (nicht als Modal).
        """
        if self._busy:
            return

        def log(line: str) -> None:
            # Thread-safe: via after ins GUI-Thread schicken.
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                fn(log)
                self.after(0, lambda: self._log.append(f"{label} abgeschlossen.", kind="success"))
            except Exception as e:  # noqa: BLE001
                msg = f"{label} nicht abgeschlossen: {e}"
                self.after(0, lambda: self._log.append(msg, kind="error"))
                self.after(
                    0,
                    lambda: self._banner.set_text(
                        f"{label} fehlgeschlagen. Internetverbindung prüfen und "
                        "erneut versuchen.",
                        "error",
                    ),
                )
            finally:
                self.after(0, self._end_busy)

        self._begin_busy(label)
        threading.Thread(target=worker, daemon=True).start()

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
            b.state(["disabled"])
        self._busy_bar.start(f"{label} läuft …")
        self._banner.set_text(f"{label} läuft …", "warning")

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
            b.state(["!disabled"])
        self._busy_bar.stop()
        # Nach install/update können die Repos neu da sein → Form neu laden.
        self._load_form_into_fields()
        self._refresh_status()

    # --- Status ------------------------------------------------------------

    def is_running(self) -> bool:
        """Für das Start-Dashboard (``gui/tab_home.py``): läuft der Server?"""
        return self._manager.is_running()

    def _refresh_status(self) -> None:
        """Lokaler Git-Status + Server-Lauf-Status als Banner-Ampel."""
        installed = all(gitops.status(name).installed for name in aa.AUSLEIHE_REPOS)
        running = self._manager.is_running()
        if running:
            self._banner.set_text("Ausleihe läuft. Danach nicht vergessen zu beenden.", "success")
        elif installed:
            self._banner.set_text(
                "Ausleihe eingerichtet und beendet. Bereit für „Ausleihe starten“.", "info"
            )
        else:
            self._banner.set_text(
                "Noch nicht eingerichtet. Zuerst „Einrichtung“ klicken.", "warning"
            )


def build(parent: tk.Widget) -> AusleiheTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return AusleiheTab(parent)
