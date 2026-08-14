"""Ersteinrichtungs-Assistent — führt linear durch alle nötigen Schritte.

Ersetzt das bisherige "man muss selbst wissen, welchen Tab man zuerst öffnet"
durch einen geführten Ablauf: Ausleihe & Ausgabe einrichten → Zugangsdaten
eintragen → Bestandsliste einrichten (optional) → Barcode-Scanner einrichten
(optional). Ruft ausschließlich vorhandene ``core``-Funktionen auf (kein neuer
Orchestrierungscode) — identisch zu den Aktionen, die die einzelnen Tabs auch
selbst anbieten. Der Assistent ist jederzeit schließbar und über den
Start-Tab erneut zu öffnen; nichts hier ist Pflicht für die Bedienung.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from core import ausleihe_ausgabe as aa
from core import barcode as bc
from core import bestand as bst
from core import envtool
from gui import theme
from gui._home_logic import ausleihe_installed as _ausleihe_installed
from gui._home_logic import barcode_installed as _barcode_installed
from gui._home_logic import bestand_installed as _bestand_installed
from gui.widgets import Banner, BusyBar, Eyebrow, FormField, LogView

LogFn = Callable[[str], None]


class _InstallStep:
    """Ein Einrichtungs-Schritt, der eine ``core``-Installfunktion aufruft."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        run: Callable[[LogFn], None],
        ready_check: Callable[[], bool],
        required: bool,
    ) -> None:
        self.title = title
        self.subtitle = subtitle
        self.run = run
        self.ready_check = ready_check
        self.required = required


_INSTALL_STEPS: tuple[_InstallStep, ...] = (
    _InstallStep(
        "Ausleihe & Ausgabe einrichten",
        "Lädt die benötigten Teile herunter und bereitet die Ausleihe vor. "
        "Das kann beim ersten Mal einige Minuten dauern.",
        aa.install,
        _ausleihe_installed,
        required=True,
    ),
    _InstallStep(
        "Bestandsliste einrichten",
        "Nur nötig, wenn die jährliche Excel-Bestandsliste genutzt werden soll. "
        "Kann übersprungen und später im Tab „Bestandsliste“ nachgeholt werden.",
        bst.install,
        _bestand_installed,
        required=False,
    ),
    _InstallStep(
        "Barcode-Scanner einrichten",
        "Nur nötig, wenn der eigenständige Barcode-Scanner im SBA-Team "
        "verwendet werden soll. Kann übersprungen werden.",
        bc.install,
        _barcode_installed,
        required=False,
    ),
)


class SetupWizard(tk.Toplevel):
    """Geführter Ablauf: Einrichtung → Zugangsdaten → optionale Werkzeuge.

    ``on_finish`` wird beim Schließen gerufen (z. B. um das Start-Dashboard
    neu zu laden) — unabhängig davon, wie weit der Assistent kam.
    """

    # Schritt-Indizes: 0=Ausleihe-Install, 1=Zugangsdaten, 2=Bestand, 3=Barcode.
    _ENV_STEP_INDEX = 1
    _TOTAL_STEPS = 4

    def __init__(self, parent: tk.Widget, on_finish: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.title("Ersteinrichtung — SBA-Launcher")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.geometry("720x560")
        self._on_finish = on_finish
        self._step = 0
        self._busy = False

        self._header = ttk.Label(self, text="", style=theme.HEADING_LABEL)
        self._header.pack(anchor="w", padx=theme.SP_XL, pady=(theme.SP_XL, theme.SP_XS))
        # Schritt-Anzeige: Punkt je Schritt, der aktuelle akzentuiert.
        # tk.Label (nicht ttk) — ``foreground`` ist per-Widget steuerbar; bei
        # ttk.Label wäre es stil-gesteuert und nicht einzeln setzbar.
        self._indicator = ttk.Frame(self)
        self._indicator.pack(anchor="w", padx=theme.SP_XL, pady=(0, theme.SP_SM))
        self._dots: list[tk.Label] = []
        for _i in range(self._TOTAL_STEPS):
            dot = tk.Label(
                self._indicator, text="●", font=theme.BODY_BOLD,
                background=theme.BG, foreground=theme.TEXT_MUTED,
            )
            dot.pack(side="left", padx=(0, theme.SP_SM))
            self._dots.append(dot)

        self._banner = Banner(self, "")
        self._banner.pack(fill="x", padx=theme.SP_XL)

        self._body = ttk.Frame(self)
        self._body.pack(fill="both", expand=True, padx=theme.SP_XL, pady=theme.SP_MD)

        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=theme.SP_XL, pady=(0, theme.SP_XL))
        self._btn_back = ttk.Button(
            nav, text="Zurück", style=theme.SECONDARY_BUTTON, command=self._go_back
        )
        self._btn_back.pack(side="left")
        self._btn_skip = ttk.Button(
            nav, text="Überspringen", style=theme.SECONDARY_BUTTON, command=self._go_next
        )
        self._btn_skip.pack(side="right", padx=(theme.SP_XS, 0))
        self._btn_next = ttk.Button(
            nav, text="Weiter", style=theme.PRIMARY_BUTTON, command=self._go_next
        )
        self._btn_next.pack(side="right")
        self._btn_close = ttk.Button(nav, text="Schließen", command=self._close)
        self._btn_close.pack(side="left", padx=(theme.SP_SM, 0))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._render_step()

    # --- Navigation ----------------------------------------------------

    def _go_back(self) -> None:
        if self._busy or self._step == 0:
            return
        self._step -= 1
        self._render_step()

    def _go_next(self) -> None:
        if self._busy:
            return
        if self._step >= self._TOTAL_STEPS - 1:
            self._close()
            return
        self._step += 1
        self._render_step()

    def _close(self) -> None:
        if self._busy:
            messagebox.showinfo(
                "Einrichtung läuft",
                "Die Einrichtung läuft noch. Bitte warten, bis sie abgeschlossen ist.",
                parent=self,
            )
            return
        if self._on_finish is not None:
            self._on_finish()
        self.destroy()

    def _clear_body(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()

    def _render_step(self) -> None:
        self._clear_body()
        self._btn_back.state(["!disabled"] if self._step > 0 else ["disabled"])
        self._btn_next.configure(text="Fertig" if self._step == self._TOTAL_STEPS - 1 else "Weiter")
        # Aktiver Schritt als Akzent-Punkt, zurückliegende als ausgefüllt, kommende
        # als blass — gibt Orientierung ohne Bewegung (Tk kann keine Spring-Anim).
        for i, dot in enumerate(self._dots):
            if i == self._step:
                dot.configure(text="●", foreground=theme.ACCENT)
            elif i < self._step:
                dot.configure(text="●", foreground=theme.TEXT_MUTED)
            else:
                dot.configure(text="○", foreground=theme.TEXT_MUTED)
        if self._step == self._ENV_STEP_INDEX:
            self._render_env_step()
        else:
            install_idx = self._step if self._step < self._ENV_STEP_INDEX else self._step - 1
            self._render_install_step(_INSTALL_STEPS[install_idx])

    # --- Install-Schritte ------------------------------------------------

    def _render_install_step(self, step: _InstallStep) -> None:
        self._header.configure(
            text=f"Schritt {self._step + 1} von {self._TOTAL_STEPS}: {step.title}"
        )
        ttk.Label(
            self._body, text=step.subtitle, style=theme.MUTED_LABEL,
            wraplength=620, justify="left",
        ).pack(anchor="w", pady=(0, theme.SP_MD))

        already_ready = step.ready_check()
        if already_ready:
            self._banner.set_text("Bereits eingerichtet — weiter geht's.", "success")
        elif step.required:
            self._banner.set_text("Dieser Schritt ist für die Ausleihe nötig.", "info")
        else:
            self._banner.set_text("Optional — kann übersprungen werden.", "info")
        self._btn_skip.state(["!disabled"] if not step.required else ["disabled"])
        self._btn_next.state(["!disabled"] if already_ready else ["disabled"])

        busy = BusyBar(self._body)
        log = LogView(self._body, height=10)
        btn = ttk.Button(
            self._body,
            text="Jetzt einrichten",
            style=theme.PRIMARY_BUTTON,
            command=lambda: self._run_install(step, log, busy),
        )
        btn.pack(anchor="w", pady=(0, theme.SP_SM))
        busy.pack(fill="x", pady=(0, theme.SP_SM))
        Eyebrow(self._body, text="Protokoll · für die Fehlersuche").pack(
            anchor="w", pady=(0, theme.SP_XS)
        )
        log.pack(fill="both", expand=True)
        self._install_button = btn

    def _run_install(self, step: _InstallStep, log: LogView, busy: BusyBar) -> None:
        if self._busy:
            return
        self._busy = True
        self._install_button.state(["disabled"])
        self._btn_next.state(["disabled"])
        self._btn_skip.state(["disabled"])
        self._btn_back.state(["disabled"])
        busy.start("Einrichtung läuft …")

        def log_line(line: str) -> None:
            self.after(0, lambda: log.append(line))

        def worker() -> None:
            try:
                step.run(log_line)
                self.after(0, lambda: self._install_done(step, log, busy, ok=True))
            except Exception as e:  # noqa: BLE001 — Assistent fängt alles und zeigt es an
                msg = str(e)
                self.after(0, lambda: self._install_done(step, log, busy, ok=False, error=msg))

        threading.Thread(target=worker, daemon=True).start()

    def _install_done(
        self, step: _InstallStep, log: LogView, busy: BusyBar, ok: bool, error: str = ""
    ) -> None:
        if not self.winfo_exists():
            return
        busy.stop()
        self._busy = False
        self._btn_back.state(["!disabled"])
        self._btn_skip.state(["!disabled"] if not step.required else ["disabled"])
        if ok:
            log.append("Einrichtung abgeschlossen.", kind="success")
            self._banner.set_text("Fertig — weiter geht's.", "success")
            self._btn_next.state(["!disabled"])
        else:
            log.append(f"Einrichtung nicht abgeschlossen: {error}", kind="error")
            self._banner.set_text(
                "Das hat nicht geklappt. Internetverbindung prüfen und erneut versuchen.",
                "error",
            )
            self._install_button.state(["!disabled"])

    # --- Zugangsdaten-Schritt --------------------------------------------

    def _render_env_step(self) -> None:
        self._header.configure(
            text=f"Schritt {self._step + 1} von {self._TOTAL_STEPS}: Zugangsdaten eintragen"
        )
        if not _ausleihe_installed():
            self._banner.set_text(
                "Bitte zuerst Schritt 1 (Ausleihe & Ausgabe einrichten) abschließen.",
                "warning",
            )
            self._btn_next.state(["disabled"])
            self._btn_skip.state(["!disabled"])
            return
        self._banner.set_text(
            "Die Angaben bleiben auf diesem Laptop. Passwörter werden nirgends angezeigt.",
            "info",
        )
        self._btn_skip.state(["!disabled"])
        self._btn_next.state(["!disabled"])

        fields: dict[str, FormField] = {}
        values = envtool.read_form()
        for key, label, masked in envtool.FORM_FIELDS:
            f = FormField(self._body, label=label, masked=masked)
            f.set(values.get(key, ""))
            f.pack(fill="x", pady=theme.SP_XS)
            fields[key] = f

        def on_save() -> None:
            envtool.write_form({k: f.get() for k, f in fields.items()})
            self._banner.set_text("Zugangsdaten gespeichert.", "success")

        ttk.Button(
            self._body, text="Zugangsdaten speichern",
            style=theme.SECONDARY_BUTTON, command=on_save,
        ).pack(anchor="w", pady=(theme.SP_SM, 0))


def open_wizard(parent: tk.Widget, on_finish: Callable[[], None] | None = None) -> SetupWizard:
    """Öffnet den Assistenten (für ``gui/tab_home.py``)."""
    return SetupWizard(parent, on_finish=on_finish)
