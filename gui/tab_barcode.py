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
from gui.qrview import QrView
from gui.widgets import LogView


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
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self._btn_install = ttk.Button(top, text="Installieren", command=self.on_install)
        self._btn_install.pack(side="left", padx=(0, 4))
        self._btn_update = ttk.Button(top, text="Updaten", command=self.on_update)
        self._btn_update.pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self._btn_start = ttk.Button(top, text="Starten", command=self.on_start)
        self._btn_start.pack(side="left", padx=4)
        self._btn_stop = ttk.Button(top, text="Stoppen", command=self.on_stop)
        self._btn_stop.pack(side="left", padx=4)

        self._status = ttk.Label(top, text="…")
        self._status.pack(side="right")

        # Mitte: Log (Server+Client) links, QR rechts.
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        self._log = LogView(mid, height=20)
        self._log.pack(side="left", fill="both", expand=True)
        self._qr = QrView(mid)
        self._qr.pack(side="right", fill="y", padx=(8, 0))
        self._log.append(
            "Bereit. Erst 'Installieren' (klont barcode-simple, npm install, "
            "Client-Venv, portables Node), dann 'Starten'."
        )
        self._log.append(
            "Hinweis: Der Server druckt beim Start einen ASCII-QR ins Log — "
            "zusätzlich erscheint der grafische QR rechts (sobald die URL "
            "geparst ist). Zertifikat-Warnung am Handy ist erwartet."
        )

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Installieren", bc.install)

    def on_update(self) -> None:
        self._run_async("Updaten", bc.update)

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
                    lambda: self._log.append("[Starten] fertig — Server + Client laufen."),
                )
            except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt
                msg = f"[Starten FEHLER] {e}"
                self.after(0, lambda: self._log.append(msg))
            finally:
                self.after(0, self._end_busy)

        self._begin_busy("Starten")
        threading.Thread(target=worker, daemon=True).start()

    def on_stop(self) -> None:
        if not (self._server_mgr.is_running() or self._client_mgr.is_running()):
            self._log.append("Server/Client laufen nicht.")
            return
        codes = bc.stop(
            self._server_mgr, self._client_mgr, log=lambda line: self._log.append(line)
        )
        self._log.append(
            f"gestoppt — Server (Exit {codes['server']}), Client (Exit {codes['client']})."
        )
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
                self.after(0, lambda: self._log.append(f"[{label}] fertig."))
            except Exception as e:  # noqa: BLE001
                msg = f"[{label} FEHLER] {e}"
                self.after(0, lambda: self._log.append(msg))
            finally:
                self.after(0, self._end_busy)

        self._begin_busy(label)
        threading.Thread(target=worker, daemon=True).start()

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
            b.state(["disabled"])
        self._status.configure(text=f"{label} …")

    def _end_busy(self) -> None:
        self._busy = False
        for b in (self._btn_install, self._btn_update, self._btn_start, self._btn_stop):
            b.state(["!disabled"])
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
            self._log.append(f"[client] {ln}")
        self.after(interval_ms, lambda: self._poll_streams(interval_ms))

    # --- Status ------------------------------------------------------------

    def _refresh_status(self) -> None:
        """Git-Status von barcode-simple + Lauf-Status beider Prozesse."""
        st = gitops.status("barcode-simple")
        if not st.installed:
            repo = "barcode-simple: fehlt"
        else:
            dirty = " (dirty)" if st.dirty else ""
            repo = f"barcode-simple: {st.branch or '?'}{dirty}"
        parts = [repo]
        if self._server_mgr.is_running():
            parts.append("Server läuft")
        if self._client_mgr.is_running():
            parts.append("Client läuft")
        if not (self._server_mgr.is_running() or self._client_mgr.is_running()):
            parts.append("gestoppt")
        self._status.configure(text="  |  ".join(parts))


def build(parent: tk.Widget) -> BarcodeTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return BarcodeTab(parent)
