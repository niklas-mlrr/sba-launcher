"""QR-View für den Barcode-Tab — rendert die Scanner-URL als grafischen QR.

Die Scanner-URL (``https://<ip>:<port>/#s=<scannerToken>``) wird aus dem
Server-stdout geparst (:func:`core.barcode.parse_scanner_url`), da
``session.json`` nur das ``desktopToken`` enthält, nicht den ``scannerToken``.
``gui/qrview.py`` nimmt die fertige URL und rendert sie via ``qrcode[pil]``
in ein ``ImageTk.PhotoImage`` — kein ASCII-Art-Parsing nötig.

Robustheit: ist ``Pillow``/``ImageTk`` nicht verfügbar (z. B. Headless-Box
ohne Tk), fällt :meth:`QrView.set_url` auf einen Hinweis-Text zurück statt zu
crashen. Das ASCII-QR aus dem Server-stdout erscheint ohnehin im LogView
(Minimum); der grafische QR ist das Nice-to-have.

tkinter-Modul → nicht auf dem headless VPS testbar, nur ``py_compile`` +
manueller Smoke auf dem Windows-Laptop.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Pillow kommt via ``qrcode[pil]`` mit; ImageTk braucht ein Tk-Build von Pillow.
# Import-Fehler werden zur Laufzeit in set_url abgefangen, nicht beim Modul-Import.
try:  # pragma: no cover — Import-Verfügbarkeit hängt am Build
    import qrcode
    from PIL import ImageTk
    _PIL_OK = True
except Exception:  # noqa: BLE001 — Headless/ohne Tk: grafischer QR deaktiviert
    _PIL_OK = False

# Kantenglättung via nächstgelegenen Nachbar beim Hochskalieren — QR bleibt
# scanbar (kein Blur, das Scanner verwirren würde).
_QR_BOX = 8  # Module-Größe im QR-Bild (px pro Modul)
_QR_BORDER = 4  # Ruhezone um den QR (Module)


class QrView(ttk.Frame):
    """Zeigt einen grafischen QR + die URL als Text (kopierbar).

    Nutzung: ``set_url(url)`` rendert den QR; ``clear()`` entfernt ihn
    (z. B. beim Stoppen). Ohne Pillow zeigt das Widget nur die URL als Text.
    """

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._photo: tk.PhotoImage | None = None  # Referenz halten (GC!)

        self._qr_label = ttk.Label(self, anchor="center")
        self._qr_label.pack(pady=(4, 2))

        self._url_var = tk.StringVar()
        url_entry = ttk.Entry(self, textvariable=self._url_var, state="readonly", width=52)
        url_entry.pack(fill="x", padx=4, pady=(2, 4))
        self._hint = ttk.Label(self, text="", foreground="#888", justify="left", wraplength=460)
        self._hint.pack(anchor="w", padx=4)

        self.clear()

    def set_url(self, url: str) -> None:
        """Rendert den QR für ``url`` und zeigt die URL als Text an."""
        self._url_var.set(url)
        if not _PIL_OK:
            self._qr_label.configure(
                image="", text="(grafischer QR deaktiviert — siehe ASCII-QR im Log)"
            )
            self._hint.configure(text="Mit Handy scannen (ASCII-QR siehe Log oben).")
            return
        # QR als PIL-Image → ImageTk.PhotoImage. border=4 = Ruhezone (Scan-Erfolg).
        img = qrcode.make(url, box_size=_QR_BOX, border=_QR_BORDER)
        self._photo = ImageTk.PhotoImage(img)
        self._qr_label.configure(image=self._photo, text="")
        self._hint.configure(
            text="Mit Handy scannen — öffnet den Scanner im Browser "
            "(Zertifikat-Warnung akzeptieren)."
        )

    def clear(self) -> None:
        """Entfernt QR + URL (z. B. beim Stoppen)."""
        self._photo = None
        self._qr_label.configure(image="", text="Noch keine Scanner-URL — Server starten.")
        self._url_var.set("")
        self._hint.configure(text="")
