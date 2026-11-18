# Einsatzbescheinigung

Desktop-App für macOS, Windows und Linux – und als **Browser-Version ohne Installation**. Sie
erstellt für mehrere Kameraden in einem Durchgang **Bescheinigungen über die Teilnahme an einem
Einsatz** (zur Vorlage beim Arbeitgeber) als PDF und bereitet für jeden Kameraden einen
**E-Mail-Entwurf mit PDF-Anhang** vor.

**Ohne Installation im Browser starten: https://cptcool.github.io/Einsatzbescheinigung/**
(z. B. auf einem Firmenrechner ohne Administratorrechte – siehe [Browser-Version](#browser-version)).

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

- **Ohne Installation**: https://cptcool.github.io/Einsatzbescheinigung/ im Browser öffnen
  (siehe [Browser-Version](#browser-version)).
- **macOS** (Apple Silicon): `Einsatzbescheinigung-macOS.zip` entpacken und die App in *Programme*
  ziehen. Die App ist nicht von Apple signiert. Beim ersten Start daher per Rechtsklick › *Öffnen*
  starten, oder unter *Systemeinstellungen › Datenschutz & Sicherheit* „Dennoch öffnen“ wählen.
- **Windows**: `Einsatzbescheinigung-Windows.exe` starten. Erscheint die SmartScreen-Warnung, auf
  *Weitere Informationen › Trotzdem ausführen* klicken.
- **Linux**: `tar -xzf Einsatzbescheinigung-Linux.tar.gz && ./Einsatzbescheinigung`

Eine neue Version entsteht durch ein Git-Tag, z. B. `git tag v1.2.1 && git push origin v1.2.1`
(vorher `__version__` in `einsatzapp/__init__.py` anpassen).

### Aus dem Quelltext starten

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip ...
.venv/bin/python main.py
```

Benötigt Python ≥ 3.10 mit Tkinter. Tests: `python -m unittest discover -s tests -t .`

## Browser-Version

Die Browser-Version läuft komplett im Browser (Edge, Chrome, Firefox oder Safari in aktueller
Version) und braucht weder Installation noch Administratorrechte. Python läuft dafür per
[Pyodide](https://pyodide.org) direkt im Browser – mit **demselben Code** wie die Desktop-App,
die PDFs sind also identisch. Bedienung und Bereiche sind die gleichen.

- **Daten bleiben auf dem Rechner.** Kontakte, Vorlage, Einstellungen und die erstellten PDFs
  liegen nur im Speicher dieses Browsers (IndexedDB) und werden an keinen Server übertragen.
  Die Website selbst lädt nichts von fremden Servern nach.
- **Datensicherung.** Werden die Browserdaten gelöscht (von Hand oder per Firmenrichtlinie beim
  Schließen), sind die Daten weg. Unter *Einstellungen › Datensicherung herunterladen* entsteht
  eine ZIP-Datei, die sich auch in einem anderen Browser oder auf einem anderen Rechner einspielen
  lässt. Vorlagen (`.einsatzvorlage`) und Kontaktlisten (CSV/Excel) sind mit der Desktop-App
  austauschbar.
- **E-Mail-Entwürfe.** Ein Browser darf Outlook & Co. nicht fernsteuern, und an einen
  `mailto:`-Link lässt sich kein Anhang hängen (kein Standard; Mailprogramme ignorieren
  `attach=`-Parameter aus Sicherheitsgründen – getestet mit Apple Mail und Thunderbird). Deshalb
  gibt es je Kamerad drei Wege:
  - **✉ E-Mail öffnen** + **📄 PDF hineinziehen**: öffnet eine neue Mail mit Empfänger, Betreff
    und Text; danach die Kachel mit der Maus ins Mail-Fenster ziehen (Chrome und Edge legen die
    Datei dabei selbst ab). Funktioniert mit jedem Mailprogramm.
  - **E-Mail-Entwurf (.eml)**: fertiger Entwurf mit PDF-Anhang zum Herunterladen und Öffnen –
    Outlook (klassisch) und Thunderbird zeigen ihn als bearbeitbaren Entwurf.
  - **Teilen …**: übergibt PDF, Betreff und Text an das Teilen-Menü des Systems (z. B. Apple Mail);
    die E-Mail-Adresse liegt dann in der Zwischenablage.

  Alles auf einmal (PDFs und .eml-Entwürfe) gibt es als ZIP.
- **Schrift.** Im Browser wird immer die maßgleiche *Liberation Sans Narrow* verwendet (Arial
  Narrow ist dort nicht verfügbar) – das Layout bleibt gleich.
- Die App sollte nur in **einem** Tab geöffnet sein; ein zweiter Tab weist darauf hin.

Die Browser-Version entsteht bei jedem Release automatisch (GitHub Actions → GitHub Pages) und
liegt dem Release außerdem als `Einsatzbescheinigung-Web.zip` bei – zum Betrieb auf einem eigenen
Webserver (z. B. im Intranet; nötig ist nur ein statischer Webserver, der `.wasm`-Dateien als
`application/wasm` ausliefert).

Selbst bauen und testen:

```bash
python tools/web_bauen.py                  # → build/web (lädt Pyodide und Pakete, prüft Prüfsummen)
python -m http.server -d build/web 8000    # dann http://localhost:8000 öffnen
npm ci --prefix tests/web && tests/web/node_modules/.bin/playwright install chromium
node tests/web/e2e.mjs build/web           # klickt den kompletten Ablauf im Browser durch
```

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
zusätzlich Python (PSF-Lizenz) und Tcl/Tk (BSD-artig), die Browser-Version Pyodide (MPL-2.0). Alle Lizenztexte zeigt die App unter
*Einstellungen › Lizenzen …*; beim Bauen werden sie von `einsatzapp/lizenzinfo.py` zusammengestellt.
