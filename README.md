# SBA-Launcher

Der SBA-Launcher ist das Startfenster für die Werkzeuge der
Schulbuchausleihe. Er ist für Nachfolgerinnen und Nachfolger gedacht, die
nicht programmieren und keine technischen Vorkenntnisse haben.

Die wichtigsten Regeln:

- Der Tab „Start“ zeigt auf einen Blick, was schon eingerichtet ist, und
  öffnet mit „Ersteinrichtung starten“ einen geführten Assistenten.
- Im Alltag werden die großen, blauen Schaltflächen in den Tabs verwendet.
- Ein rot markierter Knopf (z. B. „Excel aktualisieren“) verändert Daten —
  hier lohnt sich ein zweiter Blick, bevor bestätigt wird.
- Bei der Bestandsliste immer zuerst „Erst prüfen (nichts ändern)“ anklicken.
- Wenn etwas nicht funktioniert, ist der USB-Handscanner im offiziellen
  IServ-Ausleihe-Frontend der dauerhafte Notnagel.

## 1. Das Fenster öffnen

Der Launcher liegt auf dem Ausleihe-Laptop zum Beispiel in
C:\SBA\sba-launcher.

1. Den Ordner im Windows-Explorer öffnen.
2. „start.bat“ doppelt anklicken.
3. Warten, bis das Fenster „SBA-Launcher – Schulbuchausleihe“ erscheint.

Beim ersten Start werden benötigte Grundprogramme automatisch vorbereitet. Das
Fenster darf währenddessen nicht geschlossen werden. Eine Internetverbindung
wird nur für die Einrichtung oder eine Aktualisierung benötigt.

Hinweis: Fehlt `uv`, lädt `start.bat` es automatisch per
`irm https://astral.sh/uv/install.ps1 | iex` herunter — ohne Prüfsummenprüfung
(Vertrauen auf das TLS-Zertifikat von astral.sh). Schlägt das fehl, zeigt
`start.bat` die manuelle Installationsanleitung
(https://docs.astral.sh/uv/getting-started/installation/) an.

## 2. Einmalige Einrichtung

Die Einrichtung muss normalerweise nur einmal pro Laptop gemacht werden.

Am einfachsten im Tab „Start“ auf „Ersteinrichtung starten“ klicken — der
Assistent führt nacheinander durch Ausleihe & Ausgabe, Zugangsdaten,
Bestandsliste (optional) und Barcode-Scanner (optional). Jeder Schritt lässt
sich überspringen und später im jeweiligen Tab nachholen. Alternativ können
die folgenden Schritte auch einzeln in den Tabs ausgeführt werden: Die
Status-Leiste oben zeigt, was fehlt, und hat oft schon den passenden Knopf
dabei. „Einrichtung“ und „Aktualisieren“ liegen eingeklappt unter
„Verwaltung · nur bei der Einrichtung / selten“.

### Ausleihe & Ausgabe

1. Den Tab „Ausleihe & Ausgabe“ öffnen.
2. Die „Verwaltung“ ausklappen und auf „Einrichtung“ klicken, dann warten,
   bis sie abgeschlossen ist.
3. Die Zugangsdaten eintragen:
   - IServ-Adresse und Benutzername des dafür vorgesehenen SBA-Kontos
   - IServ-Passwort
   - ein selbst festgelegtes Passwort für das Arbeitsfenster
4. Auf „Zugangsdaten speichern“ klicken.

Die Zugangsdaten gehören zum SBA-Team. Sie dürfen nicht verschickt, in den
Chat kopiert oder in ein Protokoll geschrieben werden.

Für den Leihschein-Druck sollte ein USB-Drucker angeschlossen und in Windows
als Standarddrucker eingerichtet sein. Die ausführliche Anleitung im Hilfe-Tab
erklärt auch den ersten Browser-Aufruf und die Zertifikat-Warnung.

### Bestandsliste

Wenn die jährliche Excel-Bestandsliste genutzt werden soll:

1. Den Tab „Bestandsliste“ öffnen.
2. Die „Verwaltung“ ausklappen und auf „Einrichtung“ klicken.
3. Warten, bis die Einrichtung abgeschlossen ist.

Die Bestandsliste kann unabhängig vom Ausleihe-Tab eingerichtet werden. Die
IServ-Zugangsdaten werden nach der Einrichtung im Ausleihe-Tab gespeichert.

### Barcode-Scanner

Der Tab „Barcode-Scanner“ ist für den eigenständigen Scanner. Er muss nur
eingerichtet werden, wenn dieser Ablauf im SBA-Team verwendet werden soll:

1. Tab „Barcode-Scanner“ öffnen.
2. Die „Verwaltung“ ausklappen und auf „Einrichtung“ klicken.
3. Warten, bis sie abgeschlossen ist.

## 3. Bücherstapel bearbeiten

Das ist der normale Ablauf während der Ausgabe:

1. Laptop mit dem Schul-WLAN verbinden und Drucker einschalten.
2. Im Tab „Ausleihe & Ausgabe“ auf „Ausleihe starten“ klicken. Die Status-Leiste
   oben zeigt, ob das Werkzeug bereit ist oder läuft.
3. „Arbeitsfenster öffnen“ klicken und mit dem Passwort für das
   Arbeitsfenster anmelden.
4. Das richtige Schuljahr und die richtige Klasse auswählen.
5. Den QR-Code für die Helfer anzeigen lassen.
6. Helfer scannen die Bücher mit ihren Handys. Bei einer Zertifikat-Warnung
   muss die lokale Seite einmal bestätigt werden.
7. Nach dem Einsatz auf „Ausleihe beenden“ klicken.

Wenn ein Handy den Laptop nicht erreicht, müssen beide Geräte im selben WLAN
sein. Die ausführliche Anleitung beschreibt außerdem, welche Meldung bei einem
falschen, verliehenen oder ausgemusterten Buch zu beachten ist.

## 4. Bestandsliste aktualisieren

Die Bestandsliste wird normalerweise einmal pro Jahr bearbeitet.

1. Im Tab „Bestandsliste“ bei „Jahres-Excel“ auf „Datei auswählen …“ klicken.
2. Die Excel-Datei des aktuellen Schuljahres auswählen.
3. Auf „Erst prüfen (nichts ändern)“ klicken.
4. Den Prüfbericht im unteren Fenster lesen. Stimmen Fächer, Jahrgänge und
   Zahlen ungefähr?
5. Nur wenn der Bericht plausibel ist: „Excel aktualisieren“ klicken.
6. Die aktualisierte Excel anschließend öffnen und stichprobenartig prüfen.

Die Prüfung liest Daten aus IServ, ändert aber die Excel-Datei nicht. Beim
echten Aktualisieren wird vorher eine Sicherungskopie angelegt. Der Vorgang
schreibt niemals Daten zurück nach IServ.

### Buchkatalog

Der Buchkatalog ordnet Fach, Jahrgang und Buchnummer einander zu. Er ist
eingeklappt unter „Buchkatalog · für Sonderfälle“; technische Einstellungen
liegen weiter eingeklappt unter „Verwaltung“.

- „Bücher aus Excel übernehmen“ liest eine vorhandene Excel in den Katalog.
- „Neue Excel aus Katalog“ erstellt eine neue Excel aus der mitgelieferten
  Vorlage. Die Vorlage muss nicht selbst gesucht werden.
- „Hinzufügen“ und „Bearbeiten“ ändern eine Buch-Zuordnung.
- „Entfernen“ entfernt eine Zuordnung zunächst nur im Fenster.
- „Katalog speichern“ speichert die Änderungen dauerhaft.
- „Verwerfen / neu laden“ lädt den zuletzt gespeicherten Stand.
- „Zuordnungen übernehmen“ wird nur verwendet, wenn die Bestandsprüfung eine
  Zuordnung ausdrücklich braucht.

Eine ISBN ist die Buchnummer, die normalerweise auf dem Buch oder seiner
Verlagsangabe steht. „Mehrere Jg.“ bedeutet Mehrjahresband: Das Buch gilt für
mehr als einen Jahrgang. Die zusätzlichen Einstellungen darunter sind für
Sonderfälle und sollten ohne Rücksprache nicht verändert werden.

## 5. Sicherheitsregel für Buchungen

Der Launcher führt keine Buchungen direkt über eine selbst programmierte
Schnittstelle aus. Er schaltet die Einstellung „ALLOW_BOOKING“ nicht um.
Diese Einstellung ist der Sicherheits-Schalter: Aus bedeutet, dass ein Scan
nur vorgemerkt wird. Bei einer echten Freigabe wird nur gebucht, wenn das Buch
im Lager liegt, die Person es bestellt hat und noch kein Buch aus derselben
Reihe ausgeliehen ist.

Buchungen dürfen nur im echten, ausdrücklich freigegebenen Einsatz erfolgen.
Zum Ausprobieren muss der Scan-Modus so vorbereitet sein, dass nur
vorgemerkt und nichts gebucht wird. Wenn unklar ist, welcher Modus aktiv ist:

1. nicht weiter scannen,
2. keine technischen Dateien oder Einstellungen ändern,
3. die verantwortliche Person im SBA-Team fragen.

## 6. Wenn etwas nicht funktioniert

- **Einrichtung bricht ab:** Internetverbindung prüfen und den Vorgang noch
  einmal starten.
- **IServ-Anmeldung scheitert:** Zugangsdaten prüfen lassen. Passwörter nicht
  in Fehlermeldungen hineinschreiben.
- **Handy findet den Laptop nicht:** Gleiches WLAN verwenden und die
  Zertifikat-Warnung einmal bestätigen.
- **Druck funktioniert nicht:** Drucker einschalten, als Standarddrucker
  auswählen und Papier prüfen.
- **IServ wurde geändert oder das Werkzeug bleibt unverständlich:** auf den
  USB-Handscanner und das offizielle IServ-Ausleihe-Frontend zurückfallen.

Der USB-Handscanner ist kein Notbehelf, der „kaputt“ geht: Er ist der
dauerhaft verfügbare Weg, mit dem die Ausleihe auch ohne den Launcher
weitergeführt werden kann. Bei einem Fehler den genauen Meldungstext oder
einen Screenshot an die verantwortliche Person weitergeben.

## 7. Ausführliche Anleitung

Im Tab „Hilfe“ können die vollständige Text-Anleitung und die PDF-Version
geöffnet werden. Die Quelle liegt im Ordner des Hauptwerkzeugs:

- „ausleihe-ausgabe/docs/nachfolge-anleitung.md“
- „ausleihe-ausgabe/docs/Nachfolge-Anleitung.pdf“

Die ausführliche Anleitung ist die maßgebliche Beschreibung für Sonderfälle,
Druckerprobleme und die sichere Nutzung im laufenden Ausleihe-Einsatz.

## Optional: technische Pflege

Dieser Abschnitt ist nur für eine technisch betreuende Person gedacht.

Der Launcher ist ein Python/Tkinter-Programm ohne gebündelte EXE. Die Tests
laufen im Launcher-Ordner mit:

```bash
uv sync
uv run pytest
uvx ruff check gui/ core/ tests/
```

Die drei Schwesterprojekte werden beim Einrichten automatisch in einem
gemeinsamen Ordner neben dem Launcher abgelegt. Zugangsdaten und lokale
Konfigurationsdateien werden nicht in das Git-Repository eingecheckt.
