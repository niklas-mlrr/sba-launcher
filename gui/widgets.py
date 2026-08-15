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
- :func:`run_async` — gemeinsamer Hintergrund-Thread-Runner für
  ``_run_async``/``_begin_busy``/``_end_busy``-artige Aktionen (Einrichtung,
  Aktualisierung, Start …), die in ``tab_ausleihe.py``, ``tab_barcode.py`` und
  ``tab_bestand.py`` bisher dreifach dupliziert sind. Fixt dabei den
  Status-Clobber-Bug (Fehlerstatus wird nicht sofort vom Erfolgs-Refresh
  überschrieben) einheitlich an einer Stelle.

Diese Module importieren tkinter → **nicht** auf dem headless VPS testbar,
nur manuell auf dem Windows-/macOS-Laptop gesmoket. Keine Logik: rein
deskriptiv, alle Zustände/Validierung liegen in ``core/``.
"""

from __future__ import annotations

import contextlib
import threading
import tkinter as tk
from collections.abc import Callable, Iterable
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
        if not self.winfo_exists():
            return
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
            with contextlib.suppress(tk.TclError):
                self.widget.after_cancel(self._job)
            self._job = None
        if self._window is not None:
            with contextlib.suppress(tk.TclError):
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
    """Auf-/zuklappbarer Zonen-Bereich für seltene/technische Einstellungen.

    Liest sich als *Zone*, nicht als Formular-Checkbox: ein klickbarer
    Abschnitts-Kopf mit Aufklapp-Glyph (▸/▾) im Subheading-Stil plus
    Hover-Feedback (§1 Response — Tk kann keine Bewegung, aber sofortige
    Farb-Rückmeldung auf Zeiger-Kontakt). Standardmäßig eingeklappt
    (``expanded=False``): schützt vor versehentlicher Bearbeitung von
    Rohkonfiguration (z. B. Bestand-Sonder-Zuordnungen) durch Personen ohne
    Rücksprache, ohne die Funktion zu verstecken. ``body`` ist der Container,
    in den der Aufrufer seine Widgets packt.
    """

    def __init__(
        self, parent: tk.Widget, title: str, expanded: bool = False, **kw
    ) -> None:
        super().__init__(parent, **kw)
        self._expanded = tk.BooleanVar(value=expanded)
        self._title = title
        header = ttk.Frame(self)
        header.pack(fill="x")
        # tk.Label (nicht ttk): foreground/background ist pro-Widget steuerbar
        # für den Hover-Tausch; bei ttk.Label wäre es stil-gebunden.
        self._glyph = tk.Label(
            header, text="▾" if expanded else "▸", font=theme.BODY_BOLD,
            background=theme.BG, foreground=theme.TEXT_MUTED, cursor="hand2",
            padx=0,
        )
        self._glyph.pack(side="left", padx=(0, theme.SP_XS))
        self._header_label = tk.Label(
            header, text=title, font=theme.SUBHEADING, background=theme.BG,
            foreground=theme.TEXT, cursor="hand2", anchor="w",
        )
        self._header_label.pack(side="left", fill="x", expand=True)
        for w in (header, self._glyph, self._header_label):
            w.bind("<Button-1>", self._toggle, add="+")
            w.bind("<Enter>", self._hover_on, add="+")
            w.bind("<Leave>", self._hover_off, add="+")
        self.body = ttk.Frame(self)
        self._sync()

    # --- Toggle + Hover ----------------------------------------------------

    def _toggle(self, _event: tk.Event | None = None) -> None:
        self._expanded.set(not self._expanded.get())
        self._sync()

    def _hover_on(self, _event: tk.Event) -> None:
        self._glyph.configure(background=theme.SURFACE_2)
        self._header_label.configure(background=theme.SURFACE_2)

    def _hover_off(self, _event: tk.Event) -> None:
        self._glyph.configure(background=theme.BG)
        self._header_label.configure(background=theme.BG)

    def _sync(self) -> None:
        is_open = self._expanded.get()
        self._glyph.configure(text="▾" if is_open else "▸")
        if is_open:
            self.body.pack(fill="both", expand=True, pady=(theme.SP_XS, 0))
        else:
            self.body.pack_forget()

    def set_title(self, title: str) -> None:
        """Passt den Abschnitts-Titel an (z. B. Zustand im Titel nachführen)."""
        self._title = title
        self._header_label.configure(text=title)

    def expand(self) -> None:
        """Klappt den Bereich auf (falls noch eingeklappt) — z. B. wenn eine
        StatusBar-Aktion die Verwaltung sichtbar machen will."""
        if not self._expanded.get():
            self._expanded.set(True)
            self._sync()


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


class Eyebrow(ttk.Label):
    """Kurzer, ehrlicher Zonen-Name über einem Abschnitt (z. B. VERWALTUNG,
    PROTOKOLL).

    Großgeschrieben + gedeckt + klein — das Tk-Äquivalent eines typografischen
    „eyebrow" (§15 Typographie: Hierarchie über Gewicht/Größe, nicht nur Größe;
    Tk kann kein Letter-Spacing). Sagt einer nicht-technischen Person ehrlich,
    dass dieser Bereich nicht zum täglichen Ablauf gehört, ohne die Funktion zu
    verstecken. „Show the common path first, advanced one level deeper" (§6).
    """

    def __init__(self, parent: tk.Widget, text: str, **kw) -> None:
        super().__init__(parent, text=text.upper(), style=theme.EYEBROW_LABEL, **kw)


class StatusBar(ttk.Frame):
    """Prominente, dauerhafte Status-Leiste pro Tab — primäre Rückmeldung.

    Ersetzt das dünne :class:`Banner` als Blickfang-Oberfläche auf jedem
    Werkzeug-Tab: ein großer Zustands-Glyph, eine Headline (Subheading), eine
    gedeckte Detail-Zeile und optional ein eingebetteter Aktions-Knopf — sodass
    eine nicht-technische Person auf einen Blick sieht, in welchem Zustand sich
    das Werkzeug befindet und was als Nächstes ansteht (§16 Wayfinding:
    „Wo bin ich? Was gibt es hier? Wie komme ich weiter?").

    ``set`` färbt die ganze Leiste neu ein und aktualisiert Text + Aktion.
    ``kind`` in ``{"info","success","warning","error"}`` nutzt die bestehende
    Status-Palette (gleiche Farben wie :class:`Banner`, nur größer/prominenter).
    ``action_style`` ist ein ttk-Button-Style-String (z. B.
    :data:`gui.theme.PRIMARY_BUTTON`); ``None`` blendet den Aktions-Knopf aus.
    """

    def __init__(
        self, parent: tk.Widget, kind: str = "info", headline: str = "",
        detail: str = "", **kw,
    ) -> None:
        super().__init__(parent, **kw)
        self._inner = tk.Frame(self, background=theme.INFO_BG)
        self._inner.pack(fill="x")
        # Großer Zustands-Glyph links.
        self._symbol = tk.Label(
            self._inner, text="", font=theme.HEADING,
            padx=theme.SP_LG, pady=theme.SP_MD,
        )
        self._symbol.pack(side="left")
        # Aktions-Slot rechts (leer bis set() einen Knopf packt) — VOR dem
        # Text-Block gepackt, damit dieser bei fill/expand die Mitte füllt und
        # der Knopf rechtsständig sitzt (Tk pack wertet in Aufruf-Reihenfolge
        # aus: links, rechts, dann Mitte mit expand).
        self._action_slot = tk.Frame(self._inner, background=theme.INFO_BG)
        self._action_slot.pack(side="right", padx=(0, theme.SP_LG), pady=theme.SP_MD)
        # Text-Block: Headline + Detail gestapelt.
        self._textcol = tk.Frame(self._inner, background=theme.INFO_BG)
        self._textcol.pack(side="left", fill="both", expand=True)
        self._headline = tk.Label(
            self._textcol, text="", font=theme.SUBHEADING, anchor="w",
            justify="left", pady=0, background=theme.INFO_BG,
        )
        self._headline.pack(fill="x", pady=(theme.SP_MD, 0))
        self._detail = tk.Label(
            self._textcol, text="", font=theme.BODY, anchor="w", justify="left",
            wraplength=700, pady=0, background=theme.INFO_BG,
            foreground=theme.TEXT_MUTED,
        )
        self._detail.pack(fill="x", pady=(0, theme.SP_MD))
        self._action: ttk.Button | None = None
        self.set(kind, headline, detail)

    def set(
        self, kind: str = "info", headline: str = "", detail: str = "",
        action_text: str | None = None,
        action_cmd: Callable[[], None] | None = None,
        action_style: str | None = None,
    ) -> None:
        """Färbt die Leiste auf ``kind`` um und setzt Text + optionale Aktion."""
        bg, fg, symbol = _BANNER_STYLES.get(kind, _BANNER_STYLES["info"])
        self._inner.configure(background=bg)
        self._symbol.configure(text=symbol, background=bg, foreground=fg)
        self._action_slot.configure(background=bg)
        self._textcol.configure(background=bg)
        self._headline.configure(text=headline, background=bg, foreground=fg)
        self._detail.configure(text=detail, background=bg, foreground=fg)
        # Aktions-Knopf neu aufbauen — ttk-Style lässt sich nach Erzeugung
        # nicht in jedem Theme sauber umpatchen, zerstören+neu ist robust.
        if self._action is not None:
            self._action.destroy()
            self._action = None
        if action_text and action_cmd:
            self._action = ttk.Button(
                self._action_slot, text=action_text,
                style=action_style or theme.PRIMARY_BUTTON, command=action_cmd,
            )
            self._action.pack()


def run_async(
    widget: tk.Widget,
    label: str,
    fn: Callable[[Callable[[str], None]], object],
    *,
    log: LogView,
    status: StatusBar,
    busy_bar: BusyBar | None = None,
    buttons: Iterable[ttk.Widget] = (),
    set_busy: Callable[[bool], None] | None = None,
    on_done: Callable[[], None] | None = None,
    running_detail: str = "Bitte warten — das kann einen Moment dauern.",
    error_headline: str | None = None,
    error_detail: str = "Internetverbindung prüfen und erneut versuchen.",
) -> None:
    """Führt ``fn(log_fn)`` in einem Hintergrund-Thread aus; GUI bleibt reaktiv.

    Gemeinsame Extraktion des ``_run_async``/``_begin_busy``/``_end_busy``-
    Musters aus ``tab_ausleihe.py``, ``tab_barcode.py`` und ``tab_bestand.py``
    (inkl. ``tab_bestand``s ``_run_run``-Variante mit ``dry_run`` — dafür
    einfach ``fn=lambda log: bst.run_auto(dry_run=dry_run, ..., log=log)``
    übergeben).

    **Ablauf:**

    1. Sofort (im GUI-Thread): ``buttons`` werden deaktiviert (``.state(["disabled"])``),
       ``busy_bar.start(...)`` (falls übergeben) und ``status.set("warning", …)``
       zeigen „läuft". ``set_busy(True)`` (falls übergeben) hält ein Caller-
       eigenes Busy-Flag synchron.
    2. In einem Daemon-Thread wird ``fn(log_fn)`` aufgerufen. ``fn`` ist eine
       core-Funktion mit Signatur ``(log: Callable[[str], None]) -> None``
       (oder beliebiger Rückgabewert, der ignoriert wird). ``log_fn`` darf
       **nur** aus dem Worker-Thread heraus aufgerufen werden — es marshalt
       intern selbst via ``widget.after(0, …)`` ins GUI-Thread, ``fn`` muss
       nichts davon wissen und darf NIE direkt auf Tk-Widgets zugreifen.
    3. Bei Erfolg (kein Exception): Erfolgszeile ins Log, Buttons werden
       wieder aktiviert, ``busy_bar.stop()``, ``set_busy(False)`` — und
       **danach** ``on_done()`` (falls übergeben). ``on_done`` ist der Ort für
       caller-spezifisches Verhalten nach Erfolg, typischerweise
       ``self._refresh_status`` (ggf. plus Formular-Neuladen o. Ä.).
    4. Bei Exception: Fehlerzeile ins Log, ``status.set("error", …)`` zeigt
       den Fehler, Buttons werden wieder aktiviert, ``busy_bar.stop()``,
       ``set_busy(False)`` — **aber ``on_done()`` wird NICHT aufgerufen.**
       Das ist der Kernfix des Status-Clobber-Bugs, der in allen drei Tabs
       dupliziert war (siehe ``tab_ausleihe.on_start``s
       „Fehlerstatus stehen lassen — kein Refresh überschreibt ihn."-
       Kommentar für das gleiche Prinzip an anderer Stelle): würde
       ``on_done`` (meist ``_refresh_status``) auch im Fehlerfall laufen,
       würde es den gerade gesetzten Fehlerstatus sofort wieder mit dem
       „normalen" Status überschreiben, bevor die Nutzerin ihn lesen kann.

    Jeder ``widget.after(0, …)``-Callback prüft zuerst ``widget.winfo_exists()``
    und tut sonst nichts — schließt die Nutzerin das Fenster, während der
    Worker noch läuft, wirft der verspätete Callback keine Exception mehr.
    Diese Prüfung setzt voraus, dass ``log``, ``status`` und ``busy_bar``
    zusammen mit ``widget`` zerstört werden (z. B. als dessen Kinder) — bei
    unabhängigem Lebenszyklus müsste zusätzlich deren Existenz geprüft werden.

    Reentrancy (verhindern, dass ein zweiter Klick während eines laufenden
    Vorgangs einen zweiten Worker startet) ist **nicht** Teil dieser Funktion
    — das bleibt Sache des Callers (bestehendes ``if self._busy: return`` vor
    dem Aufruf beibehalten).

    Beispiel-Adoption (ersetzt ``tab_ausleihe.py``s ``_run_async`` +
    ``_begin_busy``/``_end_busy``-Duo)::

        def on_install(self) -> None:
            if self._busy:
                return
            run_async(
                self, "Einrichtung", aa.install,
                log=self._log, status=self._status, busy_bar=self._busy_bar,
                buttons=(self._btn_install, self._btn_update,
                         self._btn_primary, self._btn_open),
                set_busy=lambda b: setattr(self, "_busy", b),
                on_done=self._refresh_status,
            )
    """
    buttons = list(buttons)

    def _safe(callback: Callable[[], None]) -> None:
        if not widget.winfo_exists():
            return
        callback()

    def _end_common() -> None:
        # Läuft in Erfolgs- UND Fehlerfall — rührt NIE den Status an, damit
        # ein im Fehlerfall gesetzter Fehlerstatus stehen bleibt.
        if set_busy is not None:
            set_busy(False)
        for b in buttons:
            with contextlib.suppress(tk.TclError):
                b.state(["!disabled"])
        if busy_bar is not None:
            busy_bar.stop()

    def _log_line(line: str) -> None:
        widget.after(0, lambda: _safe(lambda: log.append(line)))

    def worker() -> None:
        try:
            fn(_log_line)
        except Exception as e:  # noqa: BLE001 — GUI fängt alles und loggt, keine Modals

            def _on_error(exc: Exception = e) -> None:
                log.append(f"{label} nicht abgeschlossen: {exc}", kind="error")
                status.set("error", error_headline or f"{label} fehlgeschlagen", error_detail)
                _end_common()
                # on_done() bewusst NICHT aufrufen — siehe Docstring.

            widget.after(0, lambda: _safe(_on_error))
        else:

            def _on_success() -> None:
                log.append(f"{label} abgeschlossen.", kind="success")
                _end_common()
                if on_done is not None:
                    on_done()

            widget.after(0, lambda: _safe(_on_success))

    if set_busy is not None:
        set_busy(True)
    for b in buttons:
        b.state(["disabled"])
    if busy_bar is not None:
        busy_bar.start(f"{label} läuft …")
    status.set("warning", f"{label} läuft", running_detail)

    threading.Thread(target=worker, daemon=True).start()
