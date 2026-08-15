"""Tab: Barcode-Scanner (dünn — alle Logik in ``core.barcode``).

Zwei-Prozess-Stack: Node-Server + Python-Client, je ein
:class:`~core.process.SubprocessManager`. Aktionen: Installieren, Updaten,
Starten (async — wartet auf ``session.json``), Stoppen. LogView streamt beide
Prozesse (Server-Stdout enthält das ASCII-QR + die ``Scanner URL:``-Zeile);
:class:`gui.qrview.QrView` rendert die geparste URL als grafischen QR.

Phase 8 — Layout wie der Ausleihe-Tab (Apple-Design, Tkinter-übersetzt):
1. **Status-Leiste** (``StatusBar``) — Zustand + nächste Aktion auf einen Blick.
2. **Bedienung** — ein zustandsabhängiger Haupt-Knopf: nichts los →
   „Scanner starten” (blau); läuft → „Scanner beenden” (rot, gleiche Stelle).
3. **Verwaltung** (eingeklappt) — Einrichtung/Aktualisieren, bewusst sekundär.
4. **Protokoll** (links, ``Eyebrow``) + **QR-Code** (rechts, ``QrView``) — der
   QR ist das tägliche *Ergebnis*, kein Log; er bleibt prominent.

Dünne GUI-Regel: Install/Update/Start laufen in Hintergrund-Threads; deren
``log``-Callback hängt Zeilen thread-safe via ``after(0, …)`` ins LogView. Die
dauerhaften Prozesse streamen selbst über ihre SubprocessManager (eigener
Thread + Queue); ein gemeinsamer ``after()``-Poll drain beide Queues und
inspiziert Server-Zeilen auf die Scanner-URL.

Produktionsschutz: Barcode hat keinen IServ-Kontakt — reiner
Browser→Tastatur-Bridge. Keine Credentials im Log; der Client liest sein
Token aus ``session.json``.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from core import barcode as bc
from core import status as status_mod
from core.process import SubprocessManager
from gui import theme
from gui.qrview import QrView
from gui.widgets import (
    BusyBar,
    CollapsibleSection,
    Eyebrow,
    LogView,
    StatusBar,
    add_tooltip,
    run_async,
)


class BarcodeTab(ttk.Frame):
    """Tab-Oberfläche für den eigenständigen Barcode-Scanner."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._server_mgr = SubprocessManager()
        self._client_mgr = SubprocessManager()
        self._busy = False
        self._last_url: str | None = None
        self._build()
        self._refresh_status()
        # Gemeinsamer Poll für beide Subprocess-Streams (läuft selbst weiter).
        self._poll_streams()

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        # Kopf: Titel + Einordnung.
        header = ttk.Frame(self)
        header.pack(fill="x", padx=theme.SP_LG, pady=(theme.SP_LG, theme.SP_SM))
        ttk.Label(header, text="Barcode-Scanner", style=theme.HEADING_LABEL).pack(anchor="w")
        ttk.Label(
            header,
            text="Den eigenständigen Scanner starten und den QR-Code mit dem Handy scannen.",
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

        # Bedienung: der eine, zustandsabhängige Haupt-Knopf.
        primary = ttk.LabelFrame(self, text="Bedienung", style=theme.CARD_FRAME)
        primary.pack(fill="x", padx=theme.SP_LG, pady=theme.SP_SM)
        prow = ttk.Frame(primary, style="Card.TFrame")
        prow.pack(fill="x", padx=theme.SP_MD, pady=theme.SP_MD)
        self._btn_primary = ttk.Button(
            prow, text="Scanner starten", style=theme.PRIMARY_BUTTON, command=self.on_start
        )
        self._btn_primary.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_primary,
            "Startet den Scanner. Danach den angezeigten QR-Code mit dem Handy lesen.",
        )

        # Verwaltung: seltene / einmalige Aktionen — eingeklappt.
        self._verwaltung = CollapsibleSection(
            self, title="Verwaltung · nur bei der Einrichtung / selten", expanded=False
        )
        self._verwaltung.pack(fill="x", padx=theme.SP_LG, pady=(0, theme.SP_SM))
        self._build_verwaltung(self._verwaltung.body)

        # Mitte: Protokoll (links, sekundär) + QR-Code (rechts, tägliches Ergebnis).
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=theme.SP_LG, pady=(0, theme.SP_LG))

        log_col = ttk.Frame(mid)
        log_col.pack(side="left", fill="both", expand=True)
        Eyebrow(log_col, text="Protokoll · für die Fehlersuche").pack(
            anchor="w", pady=(0, theme.SP_XS)
        )
        self._log = LogView(log_col, height=14)
        self._log.pack(fill="both", expand=True)

        qr_col = ttk.Frame(mid)
        qr_col.pack(side="right", fill="y", padx=(theme.SP_SM, 0))
        Eyebrow(qr_col, text="QR-Code").pack(anchor="w", pady=(0, theme.SP_XS))
        self._qr = QrView(qr_col)
        self._qr.pack(fill="y", expand=True)

        self._log.append(
            "Bereit. Bei der ersten Nutzung „Einrichtung” klicken (in der Verwaltung "
            "oder über die Status-Leiste), danach „Scanner starten”."
        )
        self._log.append(
            "Nach dem Start erscheint der QR-Code rechts. Mit dem Handy scannen; "
            "bei Bedarf die ausführliche Anleitung in der Hilfe öffnen."
        )

    def _build_verwaltung(self, parent: tk.Widget) -> None:
        """Einrichtung/Aktualisieren im eingeklappten Bereich."""
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, theme.SP_XS))
        self._btn_install = ttk.Button(
            actions, text="Einrichtung", style=theme.SECONDARY_BUTTON, command=self.on_install
        )
        self._btn_install.pack(side="left", padx=(0, theme.SP_SM))
        add_tooltip(
            self._btn_install,
            "Einmalig: richtet den eigenständigen Barcode-Scanner auf diesem Laptop ein.",
        )
        self._btn_update = ttk.Button(
            actions, text="Aktualisieren", style=theme.SECONDARY_BUTTON, command=self.on_update
        )
        self._btn_update.pack(side="left")
        add_tooltip(self._btn_update, "Holt eine neue Version des Barcode-Scanners.")
        ttk.Label(
            parent, text="Einmalig / selten — im Alltag nicht nötig.", style=theme.MUTED_LABEL
        ).pack(anchor="w", pady=(0, theme.SP_MD))

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        if self._busy:
            return
        run_async(
            self, "Einrichtung", bc.install,
            log=self._log, status=self._status, busy_bar=self._busy_bar,
            buttons=(self._btn_install, self._btn_update, self._btn_primary),
            set_busy=lambda b: setattr(self, "_busy", b),
            on_done=self._refresh_status,
        )

    def on_update(self) -> None:
        if self._busy:
            return
        run_async(
            self, "Aktualisierung", bc.update,
            log=self._log, status=self._status, busy_bar=self._busy_bar,
            buttons=(self._btn_install, self._btn_update, self._btn_primary),
            set_busy=lambda b: setattr(self, "_busy", b),
            on_done=self._refresh_status,
        )

    def on_start(self) -> None:
        """Startet Server+Client in einem Hintergrund-Thread.

        ``bc.start`` blockiert bis zu 30s (Warten auf session.json) — daher
        async. Die SubprocessManager sind nach ``bc.start`` aktiv und werden
        vom ``_poll_streams``-Loop ins LogView gestreamt.
        """
        if self._busy:
            return

        def log(line: str) -> None:
            self.after(0, lambda: self._log.append(line))

        def worker() -> None:
            try:
                bc.start(self._server_mgr, self._client_mgr, log)
                self.after(
                    0,
                    lambda: self._log.append(
                        "Scanner gestartet. QR-Code mit dem Handy scannen.", kind="success"
                    ),
                )
            except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt
                msg = f"Scanner konnte nicht gestartet werden: {e}"
                self.after(0, lambda: self._log.append(msg, kind="error"))
                self.after(
                    0,
                    lambda: self._status.set(
                        "error",
                        "Start fehlgeschlagen",
                        "Wenn das nicht klappt: USB-Handscanner verwenden.",
                    ),
                )
            finally:
                self.after(0, self._end_busy)

        self._begin_busy("Starten")
        threading.Thread(target=worker, daemon=True).start()

    def on_stop(self) -> None:
        if not (self._server_mgr.is_running() or self._client_mgr.is_running()):
            self._log.append("Der Barcode-Scanner läuft gerade nicht.")
            return
        if self._busy:
            return
        # bc.stop()/manager.stop() kann bis zu ~10s je Prozess blockieren (zwei
        # sequenzielle 5s-proc.wait-Timeouts) — daher im Hintergrund-Thread,
        # sonst friert das Fenster für die Dauer spürbar ein.
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_primary):
            b.state(["disabled"])
        self._busy_bar.start("Scanner wird beendet …")

        def worker() -> None:
            bc.stop(
                self._server_mgr, self._client_mgr,
                log=lambda line: self.after(0, lambda: self._log.append(line)),
            )
            self.after(0, self._on_stop_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop_done(self) -> None:
        if not self.winfo_exists():
            return
        self._busy = False
        for b in (self._btn_install, self._btn_update):
            b.state(["!disabled"])
        self._busy_bar.stop()
        self._log.append("Barcode-Scanner beendet.", kind="success")
        self._qr.clear()
        self._last_url = None
        self._refresh_status()

    # --- Async-Hilfen ------------------------------------------------------
    #
    # ``_begin_busy``/``_end_busy`` werden noch von ``on_start`` gebraucht
    # (eigener Worker, kein einfacher ``fn(log)``-Aufruf — startet Server
    # *und* Client nacheinander mit eigenem Erfolgstext). Install/Update/Stop
    # laufen inzwischen über ``gui.widgets.run_async`` bzw. einen eigenen
    # Stop-Worker (siehe ``on_install``/``on_update``/``on_stop`` oben).

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_primary):
            b.state(["disabled"])
        self._busy_bar.start(f"{label} läuft …")
        self._status.set(
            "warning", f"{label} läuft", "Bitte warten — das kann einen Moment dauern."
        )

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update):
            b.state(["!disabled"])
        self._busy_bar.stop()
        self._refresh_status()

    # --- Stream-Poll (beide Manager + URL-Erkennung) ----------------------

    def _poll_streams(self, interval_ms: int = 200) -> None:
        """Drain beide Subprocess-Queues, hängt Zeilen ins Log, erkennt URL.

        Server-Zeilen werden auf die ``Scanner URL:``-Zeile geprüft; bei Treffer
        wird der grafische QR aktualisiert. Einmal aufgerufen, läuft der Loop
        selbst weiter (bis das Widget zerstört wird).
        """
        if not self.winfo_exists():
            return
        for ln in self._server_mgr.poll_lines():
            self._log.append(ln)
            url = bc.parse_scanner_url(ln)
            if url is not None and url != self._last_url:
                # Nur bei tatsächlicher Änderung neu aufbauen — die
                # ``Scanner URL:``-Zeile kommt sonst pro Poll gleich mehrfach.
                self._last_url = url
                self._qr.set_url(url)
        for ln in self._client_mgr.poll_lines():
            self._log.append(f"Scanner: {ln}")
        self.after(interval_ms, lambda: self._poll_streams(interval_ms))

    # --- Status ------------------------------------------------------------

    def is_running(self) -> bool:
        """Für das Start-Dashboard (``gui/tab_home.py``): läuft Server/Client?"""
        return self._server_mgr.is_running() or self._client_mgr.is_running()

    def _refresh_status(self) -> None:
        """Setzt Status-Leiste + zustandsabhängigen Haupt-Knopf neu.

        Nutzt :func:`core.status.barcode_status` als einzige Quelle (Repo +
        Node + Client-Venv), statt die Abfragen im GUI zu streuen.
        """
        running = self._server_mgr.is_running() or self._client_mgr.is_running()
        st = status_mod.barcode_status(running=running)
        if st.running:
            self._btn_primary.configure(
                text="Scanner beenden", style=theme.DANGER_BUTTON, command=self.on_stop
            )
            self._btn_primary.state(["!disabled"])
            self._status.set(
                "success",
                "Scanner läuft",
                "QR-Code mit dem Handy scannen. Nach dem Einsatz „Scanner beenden”.",
                action_text="Scanner beenden",
                action_cmd=self.on_stop,
                action_style=theme.DANGER_BUTTON,
            )
        elif st.ready:
            self._btn_primary.configure(
                text="Scanner starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["!disabled"])
            self._status.set(
                "info", "Bereit", "Auf „Scanner starten” klicken, danach den QR-Code scannen."
            )
        elif st.installed:
            self._btn_primary.configure(
                text="Scanner starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["disabled"])
            detail = st.detail[0].upper() + st.detail[1:] if st.detail else "Wird vorbereitet"
            self._status.set(
                "warning",
                "Fast bereit",
                detail + " — einen Moment warten oder die Einrichtung wiederholen.",
            )
        else:
            self._btn_primary.configure(
                text="Scanner starten", style=theme.PRIMARY_BUTTON, command=self.on_start
            )
            self._btn_primary.state(["disabled"])
            self._status.set(
                "warning",
                "Noch nicht eingerichtet",
                "Einrichtung lädt den eigenständigen Scanner (einmalig).",
                action_text="Einrichtung starten",
                action_cmd=self.on_install,
                action_style=theme.SECONDARY_BUTTON,
            )


def build(parent: tk.Widget) -> BarcodeTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return BarcodeTab(parent)
