# Einsatzbescheinigung

Desktop-App für macOS, Windows und Linux. Sie erstellt für mehrere Kameraden in einem Durchgang
**Bescheinigungen über die Teilnahme an einem Einsatz** (zur Vorlage beim Arbeitgeber) als PDF
und bereitet für jeden Kameraden einen **E-Mail-Entwurf mit PDF-Anhang** im Mailprogramm vor.

**Gesendet wird nie automatisch.** Jeder Entwurf öffnet sich im Mailprogramm und wird von Hand
geprüft und abgeschickt (Human-in-the-loop).

## Bedienung

Die App hat fünf Bereiche:

| Bereich | Wozu |
|---|---|
| **Einsatz** | Schritt 1: Einsatznummer, Beginn und Ende eintragen, Kameraden per Klick anhaken.<br>Schritt 2: Zeiten je Kamerad prüfen und bei Bedarf anpassen (↺ setzt auf die Einsatzzeit zurück). Dann **PDFs erstellen und E-Mails vorbereiten**. |
| **Gespeicherte Einsätze** | Alle erstellten Einsätze mit den bescheinigten Kameraden. Von hier aus lassen sich vergessene Kameraden nachtragen. |
| **Kontakte** | Kameraden mit Anrede, Dienstgrad, Name, Anschrift und E-Mail. Import aus CSV/Excel, Export als CSV. |
| **Vorlage** | Briefkopf (Logos), Anschrift, Infoblock, Brieftext, Unterschrift, E-Mail-Betreff/-Text und Dateiname, alles mit Platzhaltern. Vorschau als PDF. Export/Import, um die Vorlage auf einen anderen Rechner zu übertragen. |
| **Einstellungen** | Mailprogramm, Kopie (BCC) z. B. an den Löschzug, Ablageordner, Sammel-PDF, Test-Entwurf. |

Eingaben: Datum `07.04.2026` (auch `7.4.26`), Uhrzeit `11:59` (auch `1159`). Liegt das Ende vor
dem Beginn, nimmt die App automatisch den Folgetag an.

### Kamerad vergessen? Nachtragen

Jeder Einsatz wird beim Erstellen gespeichert. Um später jemanden zu ergänzen:

1. *Gespeicherte Einsätze* öffnen, den Einsatz wählen und **Kameraden ergänzen** klicken
   (oder im Bereich *Einsatz* dieselbe Einsatznummer und denselben Beginn eintragen – die App
   erkennt den Einsatz dann selbst).
2. Bereits bescheinigte Kameraden sind mit **✓ erstellt am …** markiert. Nur die fehlenden
   Kameraden anhaken und wie gewohnt fortfahren.
3. Die neuen PDFs landen im selben Ordner, die vorhandenen bleiben unverändert. Das Sammel-PDF wird
   aus allen Einzel-PDFs neu zusammengesetzt, und E-Mail-Entwürfe entstehen nur für die neuen
   Kameraden.

Wird ein bereits bescheinigter Kamerad erneut angehakt (z. B. um eine Uhrzeit zu korrigieren),
wird seine Bescheinigung neu erstellt und ersetzt.

### Ablage

Je Einsatz entsteht ein Ordner, z. B. `Dokumente/Einsatzbescheinigungen/2026-04-07_1159_Einsatz_2026-117/` mit

- `2026-04-07_1159_Einsatzbescheinigung_Mustermann_Max.pdf` (eine Datei je Kamerad)
- `2026-04-07_1159_Einsatz_2026-117_Alle_Bescheinigungen.pdf` (Sammel-PDF für die Ablage)

### Vorlage einrichten

Beim ersten Start ist die **Beispielvorlage „Löschzug 1 der Feuerwehr Musterstadt“** eingerichtet
(Zugführerin Sabine Musterfrau, mit frei erfundenen Muster-Logos und Muster-Unterschrift). Im
Bereich *Vorlage* werden Texte, Infoblock, eigene Logos und die eigene Unterschrift eingetragen;
*Vorschau-PDF* zeigt das Ergebnis.

Die Beispielvorlage liegt auch als Datei bei: `einsatzapp/beispiel/Musterstadt_LZ1.einsatzvorlage`
(über *Vorlage importieren* einlesbar). Sie wird mit `python tools/beispielvorlage_erzeugen.py`
aus den Standardtexten neu erzeugt.

### Platzhalter (Auswahl)

`{Name}` `{Vorname}` `{Nachname}` `{Dienstgrad}` `{Straße}` `{PLZ}` `{Ort}` `{Einsatznummer}`
`{Datum}` `{Beginn}` `{Ende}` `{Dauer}` `{Zeitraum}` `{Ausstellungsdatum}`. Formen je nach Anrede:
`{Herr/Frau}`, `{Herrn/Frau}`, `{seiner/ihrer}`; eine optionale dritte Form gilt für „keine Angabe“.
Die vollständige Liste steht im Bereich „Vorlage“.

### Mailprogramme

| System | Unterstützt |
|---|---|
| macOS | Apple Mail, Microsoft Outlook (klassisch), Thunderbird |
| Windows | Outlook (klassisch), Standard-Mailprogramm per MAPI (z. B. Thunderbird), Thunderbird direkt |
| Linux | Standard-Mailprogramm (xdg-email), Thunderbird |
| überall | Rückfallebene: `.eml`-Dateien (Outlook öffnet sie als Entwurf) |

„Automatisch“ erkennt das eingestellte Standard-Mailprogramm. Das *neue* Outlook (Windows/Mac)
lässt sich nicht fernsteuern; dort helfen die `.eml`-Dateien oder das klassische Outlook.

Unter macOS fragt das System beim ersten Entwurf, ob die App Mail/Outlook steuern darf. Das bitte
erlauben (änderbar unter *Systemeinstellungen › Datenschutz & Sicherheit › Automation*).

## Installation

Fertige Programme stehen unter **Releases** (gebaut von GitHub Actions):

- **macOS** (Apple Silicon): `Einsatzbescheinigung-macOS.zip` entpacken und die App in *Programme*
  ziehen. Die App ist nicht von Apple signiert. Beim ersten Start daher per Rechtsklick › *Öffnen*
  starten, oder unter *Systemeinstellungen › Datenschutz & Sicherheit* „Dennoch öffnen“ wählen.
- **Windows**: `Einsatzbescheinigung-Windows.exe` starten. Erscheint die SmartScreen-Warnung, auf
  *Weitere Informationen › Trotzdem ausführen* klicken.
- **Linux**: `tar -xzf Einsatzbescheinigung-Linux.tar.gz && ./Einsatzbescheinigung`

Eine neue Version entsteht durch ein Git-Tag, z. B. `git tag v1.1.2 && git push origin v1.1.2`
(vorher `__version__` in `einsatzapp/__init__.py` anpassen).

### Aus dem Quelltext starten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip ...
.venv/bin/python main.py
```

Benötigt Python ≥ 3.10 mit Tkinter. Tests: `python -m unittest discover -s tests -t .`

## Daten & Datenschutz

Kontakte, Vorlage (inkl. Logos und Unterschrift), gespeicherte Einsätze (mit einer Kopie der
Kontaktdaten zum Zeitpunkt der Bescheinigung) und Einstellungen liegen **nur lokal**:

- macOS: `~/Library/Application Support/Einsatzbescheinigung/`
- Windows: `%APPDATA%\Einsatzbescheinigung\`
- Linux: `~/.local/share/einsatzbescheinigung/`

Das Repository enthält bewusst **keine** echte Unterschrift, keine echten Logos und keine
personenbezogenen Daten – nur die erfundene Musterstadt-Vorlage. Die eigenen Logos und die
Unterschrift kommen über *Vorlage › Bild wählen* oder über eine exportierte `.einsatzvorlage`-Datei
auf den Rechner. Eine solche Datei enthält die Unterschrift und gehört nur in vertrauenswürdige
Hände; `.gitignore` hält sie (außer der Beispielvorlage) aus dem Repository heraus.

## Schriften

Wie im Original wird **Arial Narrow** verwendet, sofern auf dem Rechner vorhanden. Sonst nutzt die
App die mitgelieferte, maßgleiche **Liberation Sans (Narrow)** (© Red Hat, GPLv2 mit
Font-Ausnahme bzw. SIL OFL, siehe `einsatzapp/fonts/`). Das Layout bleibt dadurch identisch.

## Lizenz

Einsatzbescheinigung ist freie Software unter der [MIT-Lizenz](LICENSE).

Eingebundene Komponenten stehen unter ihren eigenen Lizenzen: fpdf2 (LGPL-3.0), pypdf
(BSD-3-Clause), openpyxl und et_xmlfile (MIT), Pillow (MIT-CMU), fontTools (MIT) sowie die
Liberation-Schriften (SIL OFL 1.1 bzw. GPLv2 mit Font-Ausnahme). Die fertigen Programme enthalten
zusätzlich Python (PSF-Lizenz) und Tcl/Tk (BSD-artig). Alle Lizenztexte zeigt die App unter
*Einstellungen › Lizenzen …*; beim Bauen werden sie von `einsatzapp/lizenzinfo.py` zusammengestellt.
