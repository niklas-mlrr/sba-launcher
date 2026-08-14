"""Wiederverwendbare Tkinter-Widgets für die Launcher-Tabs.

- :class:`LogView` — monospaced, read-only, Auto-Scroll, farbige Zeilentypen;
  pollt einen :class:`~core.process.SubprocessManager` via ``after()``
  (nicht-blockierend).
- :class:`FormField` — beschriftetes Entry, optional maskiert (Passwörter).
- :class:`Banner` — farbiger Status-Streifen (info/success/warning/error) für
  Kontext-Meldungen oben im Tab, statt grauer Fließtext-Beschriftungen.
- :class:`CollapsibleSection` — auf-/zuklappbarer Bereich für seltene/
  technische Einstellungen ("Erweitert"), standardmäßig eingeklappt.
- :class:`BusyBar` — indeterminate Fortschrittsbalken für lange Aktionen
  (Einrichtung/Aktualisierung/Lauf), statt reinem Button-Ausgrauen.
- :func:`confirm_action` — einheitlich formulierter Bestätigungsdialog für
  folgenreiche Aktionen.

Diese Module importieren tkinter → **nicht** auf dem headless VPS testbar,
nur manuell auf dem Windows-/macOS-Laptop gesmoket. Keine Logik: rein
deskriptiv, alle Zustände/Validierung liegen in ``core/``.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from core.process import SubprocessManager
from gui import theme

# Cross-Plattform-Monospace: Named-Font-String (in theme.apply konfiguriert).
# Kein Tuple — ``("TkFixedFont",)`` wäre eine Font-Beschreibung mit nicht
# existierender Family und fiele still auf Größe-Default zurück (Phase-6-Bug).
_MONO = theme.MONO

# Zeilentyp → (Vordergrundfarbe im Log). "info" bleibt die Grundfarbe.
_LOG_TAG_COLORS: dict[str, str] = {
    "success": theme.LOG_SUCCESS,
    "error": theme.LOG_ERROR,
    "warning": theme.LOG_WARNING,
}


class LogView(ttk.Frame):
    """Monospaced, read-only Log-Fenster mit Auto-Scroll und Zeilentypen.

    Zeilen werden via :meth:`append` (oder :meth:`append_lines`) ergänzt;
    ``kind`` färbt die Zeile ein (``"info"`` Standard, ``"success"``,
    ``"warning"``, ``"error"``). :meth:`poll` draint die Queue eines
    ``SubprocessManager`` und plant sich selbst neu via ``after()`` —
    blockiert nie den GUI-Thread. Subprocess-Ausgabe (z. B. IServ-Report)
    kommt immer als ``"info"`` an — sie enthält keine strukturierten
    Erfolgs-/Fehler-Marker.
    """

    def __init__(self, parent: tk.Widget, height: int = 20, **kw) -> None:
        super().__init__(parent, **kw)
        self._text = tk.Text(
            self,
            height=height,
            wrap="none",
            state="disabled",
            font=_MONO,
            background=theme.LOG_BG,
            foreground=theme.LOG_FG,
            insertbackground=theme.LOG_FG,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            padx=theme.SP_SM,
            pady=theme.SP_SM,
        )
        for kind, color in _LOG_TAG_COLORS.items():
            self._text.tag_configure(kind, foreground=color)
        scroll = ttk.Scrollbar(self, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def append(self, line: str, kind: str = "info") -> None:
        """Hängt eine Zeile an und scrollt ans Ende.

        ``kind`` in ``{"info", "success", "warning", "error"}`` — färbt die
        Zeile ein, damit Erfolg/Fehler in einer langen Ausgabe auffallen.
        """
        self._text.configure(state="normal")
        start = self._text.index("end-1c")
        self._text.insert("end", line + "\n")
        if kind in _LOG_TAG_COLORS:
            self._text.tag_add(kind, start, self._text.index("end-1c"))
        self._text.configure(state="disabled")
        self._text.see("end")

    def append_lines(self, lines: list[str], kind: str = "info") -> None:
        for ln in lines:
            self.append(ln, kind=kind)

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def poll(self, manager: SubprocessManager, interval_ms: int = 200) -> None:
        """Drain die Manager-Queue und plane den nächsten Poll.

        Einmal aufgerufen, läuft die Schleife selbst weiter (bis das Widget
        zerstört wird). Leere Queue = kein Output, kein Aufwand.
        """
        lines = manager.poll_lines()
        if lines:
            self.append_lines(lines)
        self.after(interval_ms, lambda: self.poll(manager, interval_ms))


class FormField(ttk.Frame):
    """Beschriftetes Entry-Feld; ``masked=True`` für Passwörter (show='*').

    Werte via :meth:`get`/`:meth:`set`. Keine Validierung (die liegt beim
    Aufrufer / in ``core/``).
    """

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        masked: bool = False,
        width: int = 42,
        label_width: int = 18,
        **kw,
    ) -> None:
        super().__init__(parent, **kw)
        ttk.Label(self, text=label, width=label_width, anchor="w").pack(
            side="left", padx=(0, 8)
        )
        self._var = tk.StringVar()
        self._entry = ttk.Entry(self, textvariable=self._var, width=width)
        if masked:
            self._entry.configure(show="*")
        self._entry.pack(side="left", fill="x", expand=True)

    def get(self) -> str:
        return self._var.get()

    def set(self, value: str) -> None:
        self._var.set(value)

    def focus(self) -> None:
        self._entry.focus_set()


class Tooltip:
    """Zeigt eine kurze Erklärung an, wenn der Mauszeiger ruht.

    Tooltips sind absichtlich nur Zusatzinformationen: Die Oberfläche bleibt
    auch ohne Maus (z. B. mit Tastatur) vollständig bedienbar.
    """

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 650) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._job: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event: tk.Event) -> None:
        self.hide()
        self._job = self.widget.after(self.delay_ms, self.show)

    def show(self) -> None:
        self._job = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._window.geometry(f"+{x}+{y}")
        tk.Label(
            self._window,
            text=self.text,
            justify="left",
            wraplength=380,
            background=theme.SURFACE,
            foreground=theme.TEXT,
            relief="solid",
            borderwidth=1,
            highlightbackground=theme.BORDER,
            font=theme.CAPTION,
            padx=theme.SP_SM,
            pady=theme.SP_XS,
        ).pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._window is not None:
            self._window.destroy()
            self._window = None


def add_tooltip(widget: tk.Widget, text: str) -> Tooltip:
    """Hängt eine verständliche Zusatz-Erklärung an ein Widget."""
    return Tooltip(widget, text)


# Bannerart → (Hintergrund, Text, Symbol). Symbole sind reine ASCII/Unicode-
# Zeichen (kein Emoji-Font nötig), damit sie auf jedem Windows-Laptop rendern.
_BANNER_STYLES: dict[str, tuple[str, str, str]] = {
    "info": (theme.INFO_BG, theme.INFO_TEXT, "i"),
    "success": (theme.SUCCESS_BG, theme.SUCCESS_TEXT, "✓"),
    "warning": (theme.WARNING_BG, theme.WARNING_TEXT, "!"),
    "error": (theme.ERROR_BG, theme.ERROR_TEXT, "✗"),
}


class Banner(ttk.Frame):
    """Farbiger Status-Streifen für Kontext-Meldungen oben in einem Tab.

    Ersetzt graue Fließtext-Beschriftungen ("Bereit. …") durch eine visuell
    eindeutige Ampel: ``info`` (neutral), ``success`` (grün), ``warning``
    (gelb, z. B. "läuft"), ``error`` (rot). :meth:`set_text` wechselt Text
    und Art zur Laufzeit (z. B. nach einer fehlgeschlagenen Aktion).
    """

    def __init__(self, parent: tk.Widget, text: str = "", kind: str = "info", **kw) -> None:
        super().__init__(parent, **kw)
        self._inner = tk.Frame(self, background=theme.INFO_BG)
        self._inner.pack(fill="x")
        self._symbol = tk.Label(
            self._inner, text="", font=theme.BODY_BOLD,
            padx=theme.SP_MD, pady=theme.SP_SM,
        )
        self._symbol.pack(side="left")
        self._label = tk.Label(
            self._inner, text="", anchor="w", justify="left", wraplength=820,
            font=theme.BODY, pady=theme.SP_SM,
        )
        self._label.pack(side="left", fill="x", expand=True, padx=(0, theme.SP_MD))
        self.set_text(text, kind)

    def set_text(self, text: str, kind: str = "info") -> None:
        bg, fg, symbol = _BANNER_STYLES.get(kind, _BANNER_STYLES["info"])
        self._inner.configure(background=bg)
        self._symbol.configure(text=symbol, background=bg, foreground=fg)
        self._label.configure(text=text, background=bg, foreground=fg)


class CollapsibleSection(ttk.Frame):
    """Auf-/zuklappbarer Bereich für seltene/technische Einstellungen.

    Standardmäßig eingeklappt (``expanded=False``): schützt vor versehentlicher
    Bearbeitung von Rohkonfiguration (z. B. Bestand-Sonder-Zuordnungen) durch
    Personen ohne Rücksprache, ohne die Funktion zu verstecken. ``body`` ist
    der Container, in den der Aufrufer seine Widgets packt.
    """

    def __init__(
        self, parent: tk.Widget, title: str, expanded: bool = False, **kw
    ) -> None:
        super().__init__(parent, **kw)
        self._expanded = tk.BooleanVar(value=expanded)
        header = ttk.Frame(self)
        header.pack(fill="x")
        self._toggle = ttk.Checkbutton(
            header,
            text=title,
            variable=self._expanded,
            command=self._sync,
            style="Toolbutton" if "Toolbutton" in ttk.Style().theme_names() else "TCheckbutton",
        )
        self._toggle.pack(side="left")
        self.body = ttk.Frame(self)
        self._sync()

    def _sync(self) -> None:
        if self._expanded.get():
            self.body.pack(fill="both", expand=True, pady=(4, 0))
        else:
            self.body.pack_forget()


class BusyBar(ttk.Frame):
    """Indeterminate Fortschrittsbalken + ruhige Statuszeile für lange Aktionen.

    :meth:`start` zeigt Balken und Statuszeile und beginnt die Animation;
    :meth:`stop` beendet und blendet beides aus. Ersetzt das reine Ausgrauen
    der Buttons als einziges Lauf-Signal — sichtbares Feedback, dass etwas
    passiert (Installationen können laut README mehrere Minuten dauern).
    """

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._bar = ttk.Progressbar(self, mode="indeterminate")
        self._label = ttk.Label(self, text="", style=theme.MUTED_LABEL)

    def start(self, label: str = "") -> None:
        if label:
            self._label.configure(text=label)
            self._label.pack(side="left", padx=(0, theme.SP_SM))
        self._bar.pack(side="left", fill="x", expand=True)
        self._bar.start(12)

    def stop(self) -> None:
        self._bar.stop()
        self._bar.pack_forget()
        self._label.pack_forget()


def confirm_action(parent: tk.Widget, title: str, body: str) -> bool:
    """Einheitlicher Bestätigungsdialog für folgenreiche Aktionen.

    Nutzt ein Warn-Icon konsequent für alles, was Daten überschreibt/entfernt
    — nicht nur den Bestand-Echtlauf. ``body`` sollte immer sagen, was genau
    passiert und was dabei erhalten bleibt (z. B. Sicherungskopie).
    """
    return messagebox.askyesno(title, body, icon="warning", parent=parent)
