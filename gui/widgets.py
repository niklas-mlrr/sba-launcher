"""Wiederverwendbare Tkinter-Widgets für die Launcher-Tabs.

- :class:`LogView` — monospaced, read-only, Auto-Scroll; pollt einen
  :class:`~core.process.SubprocessManager` via ``after()`` (nicht-blockierend).
- :class:`FormField` — beschriftetes Entry, optional maskiert (Passwörter).

Diese Module importieren tkinter → **nicht** auf dem headless VPS testbar,
nur manuell auf dem Windows-Laptop gesmoket. Keine Logik: rein deskriptiv,
alle Zustände/Validierung liegen in ``core/``.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.process import SubprocessManager

# Cross-Plattform-Monospace (Tk-named font; fällt überall auf eine passende
# Fixed-Font zurück — kein harter "Consolas"/"Courier"-String).
_MONO = "TkFixedFont"


class LogView(ttk.Frame):
    """Monospaced, read-only Log-Fenster mit Auto-Scroll.

    Zeilen werden via :meth:`append` (oder :meth:`append_lines`) ergänzt;
    :meth:`poll` draint die Queue eines ``SubprocessManager`` und plant sich
    selbst neu via ``after()`` — blockiert nie den GUI-Thread.
    """

    def __init__(self, parent: tk.Widget, height: int = 20, **kw) -> None:
        super().__init__(parent, **kw)
        self._text = tk.Text(
            self,
            height=height,
            wrap="none",
            state="disabled",
            font=(_MONO,),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#d4d4d4",
            relief="flat",
            padx=6,
            pady=4,
        )
        scroll = ttk.Scrollbar(self, command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def append(self, line: str) -> None:
        """Hängt eine Zeile an und scrollt ans Ende."""
        self._text.configure(state="normal")
        self._text.insert("end", line + "\n")
        self._text.configure(state="disabled")
        self._text.see("end")

    def append_lines(self, lines: list[str]) -> None:
        for ln in lines:
            self.append(ln)

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
            wraplength=360,
            background="#fffde8",
            foreground="#222222",
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=4,
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
