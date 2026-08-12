"""Tab: ausleihe-ausgabe (dünn — alle Logik in ``core.ausleihe_ausgabe``).

Aktionen: Installieren, Updaten, Server starten/stopen, Host öffnen, plus
die zentrale ``.env``-Form (IServ-Zugang + Host-Passwort), die in **beide**
Geschwister-``.env`` schreibt.

Dünne GUI-Regel: lange Operationen (install/update) laufen in einem
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
from gui.widgets import FormField, LogView

# Form-Felder: (key, label, masked). Reihenfolge = Anzeige.
_ENV_FIELDS: list[tuple[str, str, bool]] = [
    ("ISERV_DOMAIN", "IServ-Domain", False),
    ("ISERV_USERNAME", "IServ-Benutzer", False),
    ("ISERV_PASSWORD", "IServ-Passwort", True),
    ("HOST_PASSWORD", "Host-Passwort", True),
]


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
        # Aktions-Leiste (oben).
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self._btn_install = ttk.Button(top, text="Installieren", command=self.on_install)
        self._btn_install.pack(side="left", padx=(0, 4))
        self._btn_update = ttk.Button(top, text="Updaten", command=self.on_update)
        self._btn_update.pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self._btn_start = ttk.Button(top, text="Server starten", command=self.on_start)
        self._btn_start.pack(side="left", padx=4)
        self._btn_stop = ttk.Button(top, text="Server stoppen", command=self.on_stop)
        self._btn_stop.pack(side="left", padx=4)
        self._btn_open = ttk.Button(top, text="Host öffnen", command=self.on_open_host)
        self._btn_open.pack(side="left", padx=4)

        self._status = ttk.Label(top, text="…")
        self._status.pack(side="right")

        # Log (mitte).
        self._log = LogView(self, height=16)
        self._log.pack(fill="both", expand=True, padx=12, pady=4)
        self._log.append(
            "Bereit. Erst 'Installieren', dann .env ausfüllen & speichern, "
            "dann 'Server starten'. Host: " + aa.host_url()
        )
        self._log.append(
            "Hinweis: Beim Öffnen des Host im Browser erscheint eine "
            "Zertifikat-Warnung (self-signed) — das ist erwartet."
        )

        # .env-Form (unten).
        form = ttk.LabelFrame(self, text=".env — IServ-Zugang + Host-Passwort")
        form.pack(fill="x", padx=12, pady=(4, 12))
        self._fields: dict[str, FormField] = {}
        for key, label, masked in _ENV_FIELDS:
            f = FormField(form, label=label, masked=masked)
            f.pack(fill="x", padx=10, pady=2)
            self._fields[key] = f
        ttk.Button(form, text="Speichern (beide .env)", command=self.on_save_env).pack(
            anchor="w", padx=10, pady=6
        )

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
                "[.env] Repos noch nicht geklont — bitte erst 'Installieren'. "
                "Die Werte bleiben im Formular stehen und werden nach dem "
                "Klonen gespeichert."
            )
            return
        values = {key: f.get() for key, f in self._fields.items()}
        envtool.write_form(values)
        self._log.append(
            ".env gespeichert (ausleihe-ausgabe + ausleihe-api). "
            f"Host-URL: {aa.host_url()}"
        )

    # --- Aktionen ----------------------------------------------------------

    def on_install(self) -> None:
        self._run_async("Installieren", aa.install)

    def on_update(self) -> None:
        self._run_async("Updaten", aa.update)

    def on_start(self) -> None:
        try:
            aa.start_server(self._manager)
            self._log.append(f"Server gestartet — Host: {aa.host_url()}")
        except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt
            self._log.append(f"[Start FEHLER] {e}")
        self._refresh_status()

    def on_stop(self) -> None:
        if not self._manager.is_running():
            self._log.append("Server läuft nicht.")
            return
        code = aa.stop_server(self._manager)
        self._log.append(f"Server gestoppt (Exit {code}).")
        self._refresh_status()

    def on_open_host(self) -> None:
        try:
            url = aa.open_host()
            self._log.append(f"Host geöffnet: {url}")
        except Exception as e:  # noqa: BLE001
            self._log.append(f"[Öffnen FEHLER] {e}")

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
        # Nach install/update können die Repos neu da sein → Form neu laden.
        self._load_form_into_fields()
        self._refresh_status()

    # --- Status ------------------------------------------------------------

    def _refresh_status(self) -> None:
        """Lokaler Git-Status + Server-Lauf-Status (kurze Subprocess-Aufrufe)."""
        parts: list[str] = []
        for name in aa.AUSLEIHE_REPOS:
            st = gitops.status(name)
            if not st.installed:
                parts.append(f"{name}: fehlt")
            else:
                dirty = " (dirty)" if st.dirty else ""
                parts.append(f"{name}: {st.branch or '?'}{dirty}")
        running = "Server läuft" if self._manager.is_running() else "Server gestoppt"
        self._status.configure(text="  |  ".join(parts) + "  —  " + running)


def build(parent: tk.Widget) -> AusleiheTab:
    """Erzeugt den Tab-Frame und liefert ihn (für ``gui.app``)."""
    return AusleiheTab(parent)
