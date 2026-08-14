"""Hilfe-Tab für Menschen ohne Programmierkenntnisse.

Die ausführliche Nachfolge-Anleitung bleibt im ausleihe-ausgabe-Repo die
Quelle der Wahrheit. Dieser Tab beantwortet die häufigste Frage im Alltag:
"Was klicke ich jetzt?" Die Texte hier sind bewusst kurz und verweisen für
Fehlerfälle und Hintergründe auf die vollständige Anleitung.
"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from core import paths
from gui import theme

_SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "Willkommen",
        "Du brauchst keine Programmierkenntnisse. Der Tab „Start“ zeigt dir auf "
        "einen Blick, welches Werkzeug schon eingerichtet ist, und öffnet mit "
        "„Ersteinrichtung starten“ einen geführten Assistenten für den ersten "
        "Laptop. In den drei Arbeits-Tabs startest du die Werkzeuge danach mit "
        "den großen Schaltflächen.",
    ),
    (
        "Welcher Tab ist richtig?",
        "Start: Übersicht, ob alles eingerichtet ist, plus Ersteinrichtungs-"
        "Assistent. "
        "Ausleihe & Ausgabe: Bücherstapel für eine Klasse bearbeiten. "
        "Bestandsliste: die jährliche Excel-Datei aus IServ aktualisieren und "
        "sehen, welche Bücher nachbestellt werden müssen. "
        "Barcode-Scanner: den eigenständigen Scanner starten, falls dieser "
        "für den Ablauf benötigt wird.",
    ),
    (
        "Einmalige Einrichtung",
        "Am einfachsten im Tab „Start“ auf „Ersteinrichtung starten“ klicken — "
        "der Assistent führt Schritt für Schritt durch alles Nötige. "
        "Alternativ von Hand:\n"
        "1. Im Tab „Ausleihe & Ausgabe“ auf „Einrichtung“ klicken und warten, "
        "bis die Meldung „fertig“ erscheint. Das kann beim ersten Mal einige "
        "Minuten dauern.\n"
        "2. Die vier Zugangsdaten eintragen und „Zugangsdaten speichern“ "
        "klicken. Das IServ-Passwort wird nicht im Protokoll angezeigt.\n"
        "3. Nur wenn die Bestandsliste gebraucht wird: im Tab "
        "„Bestandsliste“ ebenfalls „Einrichtung“ klicken.\n"
        "Danach ist normalerweise keine Einrichtung mehr nötig. Eine "
        "„Aktualisierung“ wird nur verwendet, wenn eine neue Version angekündigt "
        "wurde oder ein Problem dadurch behoben werden soll.",
    ),
    (
        "Bücher ausgeben – normaler Ablauf",
        "1. Laptop mit dem Schul-WLAN verbinden und Drucker einschalten.\n"
        "2. „Ausleihe & Ausgabe“ öffnen und „Ausleihe starten“ klicken.\n"
        "3. „Arbeitsfenster öffnen“ klicken. Dort mit dem Host-Passwort anmelden.\n"
        "4. Klasse öffnen, QR-Code für die Helfer anzeigen und die Bücher "
        "scannen lassen.\n"
        "5. Nach dem Einsatz „Ausleihe beenden“ klicken.\n\n"
        "Eine Zertifikat-Warnung im Browser kann beim ersten Öffnen erscheinen. "
        "Bei diesem lokalen Schul-WLAN-Werkzeug ist das erwartet; die "
        "ausführliche Anleitung erklärt die Bestätigung für Edge und Firefox.",
    ),
    (
        "Bestandsliste – erst prüfen, dann schreiben",
        "1. Die Jahres-Excel mit „Datei auswählen …“ auswählen.\n"
        "2. Immer zuerst „Erst prüfen (nichts ändern)“ klicken. Dabei werden "
        "Daten aus IServ gelesen und ein Prüfbericht angezeigt; die Excel bleibt "
        "unverändert.\n"
        "3. Den Bericht prüfen. Erst wenn Fächer, Jahrgänge und Zahlen plausibel "
        "sind, „Excel aktualisieren“ klicken. Die alte Datei wird vorher gesichert.\n\n"
        "Der Buchkatalog darunter ist eine lokale Zuordnung von Fach, Jahrgang "
        "und Buchnummer (ISBN). Ein Mehrjahresband ist ein Buch, das für mehrere "
        "Jahrgänge gilt. Änderungen erst vornehmen, wenn klar ist, welche "
        "Buchnummer gemeint ist; danach „Katalog speichern“ klicken.",
    ),
    (
        "Wichtige Sicherheitsregel für Buchungen",
        "Der Launcher schaltet Buchungen nicht selbst ein und ändert keine "
        "Buchungen direkt in IServ. Die Einstellung ALLOW_BOOKING wird von ihm "
        "nicht verändert. Sie ist der Sicherheits-Schalter: Aus bedeutet, dass "
        "ein Scan nur vorgemerkt wird. Bei einer echten Freigabe wird nur gebucht, "
        "wenn das Buch im Lager liegt, die Person es bestellt hat und noch kein "
        "Buch aus derselben Reihe ausgeliehen ist.\n\n"
        "Die eigentliche Buchung läuft dabei über das offizielle IServ-"
        "Ausleihe-Fenster.\n\n"
        "Buchungen dürfen nur im echten, ausdrücklich freigegebenen Einsatz "
        "erfolgen. Für ein Ausprobieren muss der Scan-Modus so eingestellt sein, "
        "dass nur vorgemerkt und nichts gebucht wird. Wenn du nicht sicher bist: "
        "nicht scannen, nichts an Zugangsdaten oder technischen Einstellungen "
        "ändern und die verantwortliche Person fragen.",
    ),
    (
        "Wenn etwas nicht funktioniert",
        "- Internet fehlt: WLAN prüfen und Einrichtung/Aktualisierung erneut "
        "versuchen.\n"
        "- Handy erreicht den Laptop nicht: Beide Geräte müssen im selben WLAN "
        "sein; die Zertifikat-Warnung einmal bestätigen.\n"
        "- IServ-Anmeldung schlägt fehl: Zugangsdaten prüfen lassen; Passwörter "
        "nicht in den Chat oder in ein Protokoll schreiben.\n"
        "- Das Werkzeug bleibt unverständlich oder IServ wurde geändert: auf den "
        "dauerhaften Notnagel wechseln – USB-Handscanner und das offizielle "
        "IServ-Ausleihe-Frontend. Die Ausleihe kann damit weitergehen.\n\n"
        "Bei einer Fehlermeldung den genauen Text notieren oder einen Screenshot "
        "machen. Nicht selbst Dateien oder technische Einstellungen löschen.",
    ),
)


def _documentation_paths() -> tuple[Path, Path]:
    """Liefert die Markdown- und PDF-Anleitung neben dem Hauptwerkzeug."""
    docs = paths.sibling("ausleihe-ausgabe") / "docs"
    return docs / "nachfolge-anleitung.md", docs / "Nachfolge-Anleitung.pdf"


class HelpTab(ttk.Frame):
    """Scrollbare, alltagsnahe Hilfe mit Links zur vollständigen Anleitung."""

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=theme.SP_LG, pady=(theme.SP_LG, theme.SP_SM))
        ttk.Label(
            top,
            text="Kurzhilfe für das SBA-Team",
            style=theme.HEADING_LABEL,
        ).pack(anchor="w")
        ttk.Label(
            top,
            text="Hier steht, was du im Alltag anklicken musst. Für die vollständige "
            "Schritt-für-Schritt-Anleitung kannst du die Text- oder PDF-Version öffnen.",
            style=theme.MUTED_LABEL,
            justify="left",
            wraplength=860,
        ).pack(anchor="w", pady=(theme.SP_XS, theme.SP_SM))

        links = ttk.Frame(top)
        links.pack(anchor="w")
        ttk.Button(
            links,
            text="Ausführliche Anleitung öffnen",
            style=theme.SECONDARY_BUTTON,
            command=lambda: self._open_document(_documentation_paths()[0]),
        ).pack(side="left", padx=(0, theme.SP_SM))
        ttk.Button(
            links,
            text="PDF-Anleitung öffnen",
            style=theme.SECONDARY_BUTTON,
            command=lambda: self._open_document(_documentation_paths()[1]),
        ).pack(side="left")
        ttk.Label(
            top,
            text="Die ausführliche Anleitung liegt im Ordner des Hauptwerkzeugs.",
            style=theme.MUTED_LABEL,
        ).pack(anchor="w", pady=(theme.SP_SM, 0))

        body = ttk.LabelFrame(self, style=theme.CARD_FRAME)
        body.pack(fill="both", expand=True, padx=theme.SP_LG, pady=(0, theme.SP_LG))
        scroll = ttk.Scrollbar(body, orient="vertical")
        self._text = tk.Text(
            body,
            wrap="word",
            state="disabled",
            relief="flat",
            borderwidth=0,
            padx=theme.SP_MD,
            pady=theme.SP_SM,
            cursor="arrow",
            background=theme.SURFACE,
            foreground=theme.TEXT,
        )
        self._text.configure(yscrollcommand=scroll.set)
        scroll.configure(command=self._text.yview)
        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._text.tag_configure(
            "heading", font=theme.SUBHEADING, spacing1=theme.SP_MD, spacing3=theme.SP_XS,
            foreground=theme.ACCENT,
        )
        self._text.tag_configure(
            "body", font=theme.BODY, spacing1=theme.SP_XS, spacing3=theme.SP_SM,
            foreground=theme.TEXT,
        )
        self._text.configure(state="normal")
        for heading, content in _SECTIONS:
            self._text.insert("end", heading + "\n", "heading")
            self._text.insert("end", content + "\n", "body")
        self._text.configure(state="disabled")

    @staticmethod
    def _open_document(path: Path) -> None:
        if not path.is_file():
            messagebox.showerror(
                "Anleitung nicht gefunden",
                "Die ausführliche Anleitung wurde nicht gefunden. "
                "Bitte die Einrichtung prüfen oder die verantwortliche Person fragen.",
            )
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            messagebox.showerror(
                "Anleitung öffnen",
                f"Die Anleitung konnte nicht geöffnet werden: {exc}",
            )


def build(parent: tk.Widget) -> HelpTab:
    """Erzeugt den Hilfe-Tab und liefert ihn für gui.app zurück."""
    return HelpTab(parent)
