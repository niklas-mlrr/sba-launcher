"""Tab: Barcode-Scanner (dünn — alle Logik in ``core.barcode``).

Zwei-Prozess-Stack: Node-Server + Python-Client, je ein
:class:`~core.process.SubprocessManager`. Aktionen: Installieren, Updaten,
Starten (async — wartet auf ``session.json``), Stoppen. LogView streamt beide
Prozesse (Server-Stdout enthält das ASCII-QR + die ``Scanner URL:``-Zeile);
:class:`~gui.qrview.QrView` rendert die geparste URL als grafischen QR.

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
from core import gitops
from core.process import SubprocessManager
from gui import theme
from gui.qrview import QrView
from gui.widgets import Banner, BusyBar, LogView, add_tooltip


class BarcodeTab(ttk.Frame):
    """Tab-Oberfläche für den eigenständigen Barcode-Scanner."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._server_mgr = SubprocessManager()
        self._client_mgr = SubprocessManager()
        self._busy = False
        self._build()
        self._refresh_status()
        # Gemeinsamer Poll für beide Subprocess-Streams (läuft selbst weiter).
        self._poll_streams()

    # --- Aufbau ------------------------------------------------------------

    def _build(self) -> None:
        self._banner = Banner(
            self,
            "Der QR-Code rechts wird nach dem Start mit dem Handy gescannt. Eine "
            "Zertifikat-Warnung am Handy ist beim ersten Öffnen erwartet.",
        )
        self._banner.pack(fill="x", padx=12, pady=(12, 8))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(0, 4))
        self._btn_start = ttk.Button(
            top, text="Scanner starten", style=theme.PRIMARY_BUTTON, command=self.on_start
        )
        self._btn_start.pack(side="left", padx=(0, 4))
        add_tooltip(
            self._btn_start,
            "Startet den Scanner. Danach den angezeigten QR-Code mit dem Handy lesen.",
        )
        self._btn_stop = ttk.Button(top, text="Scanner beenden", command=self.on_stop)
        self._btn_stop.pack(side="left", padx=4)
        add_tooltip(self._btn_stop, "Beendet den Barcode-Scanner.")
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self._btn_install = ttk.Button(
            top, text="Einrichtung", style=theme.SECONDARY_BUTTON, command=self.on_install
        )
        self._btn_install.pack(side="left", padx=4)
        add_tooltip(
            self._btn_install,
            "Einmalig: richtet den eigenständigen Barcode-Scanner auf diesem Laptop ein.",
        )
        self._btn_update = ttk.Button(
            top, text="Aktualisieren", style=theme.SECONDARY_BUTTON, command=self.on_update
        )
        self._btn_update.pack(side="left", padx=4)
        add_tooltip(self._btn_update, "Holt eine neue Version des Barcode-Scanners.")

        self._busy_bar = BusyBar(self)
        self._busy_bar.pack(fill="x", padx=12)

        # Mitte: Log (Server+Client) links, QR rechts.
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        self._log = LogView(mid, height=20)
        self._log.pack(side="left", fill="both", expand=True)
        self._qr = QrView(mid)
        self._qr.pack(side="right", fill="y", padx=(8, 0))
        self._log.append(
            "Bereit. Bei der ersten Nutzung „Einrichtung“ klicken, danach "
            "„Scanner starten“."
        )
        self._log.append(
            "Nach dem Start erscheint der QR-Code rechts. Mit dem Handy scannen; "
            "bei Bedarf die ausführliche Anleitung in der Hilfe öffnen."
        )

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Einrichtung", bc.install)

    def on_update(self) -> None:
        self._run_async("Aktualisierung", bc.update)

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
                    lambda: self._banner.set_text(
                        "Start fehlgeschlagen. Wenn das nicht klappt: USB-Handscanner "
                        "verwenden.",
                        "error",
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
        bc.stop(
            self._server_mgr, self._client_mgr, log=lambda line: self._log.append(line)
        )
        self._log.append("Barcode-Scanner beendet.", kind="success")
        self._qr.clear()
        self._refresh_status()

    # --- Async-Hilfen ------------------------------------------------------

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

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
            b.state(["disabled"])
        self._busy_bar.start()
        self._banner.set_text(f"{label} läuft …", "warning")

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
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
        for ln in self._server_mgr.poll_lines():
            self._log.append(ln)
            url = bc.parse_scanner_url(ln)
            if url is not None:
                self._qr.set_url(url)
        for ln in self._client_mgr.poll_lines():
            self._log.append(f"Scanner: {ln}")
        self.after(interval_ms, lambda: self._poll_streams(interval_ms))

    # --- Status ------------------------------------------------------------

    def is_running(self) -> bool:
        """Für das Start-Dashboard (``gui/tab_home.py``): läuft Server/Client?"""
        return self._server_mgr.is_running() or self._client_mgr.is_running()

    def _refresh_status(self) -> None:
        """Zeigt den verständlichen Einrichtungs- und Laufstatus als Banner."""
        st = gitops.status("barcode-simple")
        running = self._server_mgr.is_running() or self._client_mgr.is_running()
        if running:
            self._banner.set_text("Scanner läuft. QR-Code mit dem Handy scannen.", "success")
        elif st.installed:
            self._banner.set_text(
                "Scanner eingerichtet und beendet. Bereit für „Scanner starten“.", "info"
            )
        else:
            self._banner.set_text(
                "Noch nicht eingerichtet. Zuerst „Einrichtung“ klicken.", "warning"
            )


def build(parent: tk.Widget) -> BarcodeTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return BarcodeTab(parent)
