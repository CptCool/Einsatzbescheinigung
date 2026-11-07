"""Speicherung von Kontakten, Vorlage und Einstellungen als JSON im Datenordner."""

import base64
import copy
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from .paths import data_dir, documents_dir, resource_dir

KONTAKT_FELDER = ["anrede", "vorname", "nachname", "dienstgrad", "strasse", "plz", "ort", "email"]

# Generische Beispielvorlage (Löschzug 1 der Feuerwehr Musterstadt). Die eigene Vorlage wird im
# Bereich „Vorlage“ eingerichtet und nur lokal gespeichert. Positionen und Größen in Millimetern.
DEFAULT_TEMPLATE = {
    "schrift": "Arial Narrow",
    "logo_links": {"datei": "", "x": 25.3, "y": 11.6, "b": 49.7, "h": 0},
    "logo_rechts": {"datei": "", "x": 151.9, "y": 9.2, "b": 48.1, "h": 27.5},
    "kopf_text": "Der Bürgermeister",
    "anschrift": "{Herrn/Frau}\n{Name}\n{Straße}\n{PLZ} {Ort}\nDeutschland",
    "infoblock": (
        "Auskunft | Frau Musterfrau\n"
        "Mein Zeichen | Freiwillige Feuerwehr Musterstadt, LZ 1\n"
        "Gebäude | Feuerwehrstraße 1\n"
        "Telefon | +49 (0) 30 / 23125 -112\n"
        "e-mail | lz1@feuerwehr-musterstadt.example\n"
        "Internet | www.feuerwehr-musterstadt.example\n"
        "Aktenzeichen | Einsatz LZ 1 {Einsatznummer}"
    ),
    "datum_bezeichnung": "Datum",
    "datum_wert": "{Ausstellungsdatum}",
    "titel": "Bescheinigung über die Teilnahme an einem Einsatz",
    "anrede": "Sehr geehrte Damen und Herren,",
    "text": (
        "hiermit bestätige ich Ihnen, dass {Herr/Frau} {Name} im Rahmen {seiner/ihrer} "
        "ehrenamtlichen Tätigkeit am {Datum} als Einsatzkraft von {Beginn} Uhr bis {Ende} Uhr "
        "im Einsatz war.\n"
        "Auf diesem Wege möchte ich mich, auch im Namen der Leitung der Feuerwehr Musterstadt, "
        "für Ihre Bereitschaft, Mitarbeiter für die Freiwillige Feuerwehr freizustellen, "
        "recht herzlich bedanken."
    ),
    "gruss": "Mit freundlichen Grüßen\nIm Auftrag",
    "unterschrift": {"datei": "", "x": 20.7, "b": 59.0, "dy": 0},
    "unterzeichner": "Sabine Musterfrau\nZugführerin Löschzug 1",
    "mail_betreff": "Einsatzbescheinigung – Einsatz {Einsatznummer} am {Datum}",
    "mail_text": (
        "Hallo {Vorname},\n\n"
        "anbei erhältst du die Bescheinigung über deine Teilnahme am Einsatz {Einsatznummer} "
        "am {Datum} ({Beginn} bis {Ende} Uhr) zur Vorlage bei deinem Arbeitgeber.\n\n"
        "Danke für deinen Einsatz!\n\n"
        "Kameradschaftliche Grüße\n"
        "Löschzug 1"
    ),
    "dateiname": "{EinsatzDatumISO}_{EinsatzBeginnHHMM}_Einsatzbescheinigung_{Nachname}_{Vorname}",
}

BILD_FELDER = ["logo_links", "logo_rechts", "unterschrift"]

DEFAULT_SETTINGS = {
    "mailprogramm": "auto",
    "bcc": "",
    "ausgabeordner": "",
    "mails_erstellen": True,
    "sammel_pdf": True,
}

VORLAGE_FORMAT = "einsatzbescheinigung-vorlage"
BEISPIELVORLAGE = "beispiel/Musterstadt_LZ1.einsatzvorlage"


def _merge(defaults: dict, data: dict) -> dict:
    result = copy.deepcopy(defaults)
    for key, value in (data or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except (OSError, ValueError):
        # Defekte Datei nicht überschreiben, sondern beiseitelegen
        backup = path.with_suffix(path.suffix + ".defekt")
        shutil.copy2(path, backup)
        return fallback


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    os.replace(tmp, path)


def sort_key(contact: dict):
    def norm(s):
        s = (s or "").casefold()
        for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
            s = s.replace(a, b)
        return s
    return (norm(contact.get("nachname")), norm(contact.get("vorname")))


class Store:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.assets = self.dir / "bilder"
        self.assets.mkdir(exist_ok=True)
        self.contacts: list[dict] = []
        self.template: dict = {}
        self.settings: dict = {}
        self.einsaetze: list[dict] = []
        self.load()

    # ------------------------------------------------------------------ Laden/Speichern
    def load(self):
        raw = _read_json(self.dir / "kontakte.json", [])
        self.contacts = [self._clean_contact(c) for c in raw if isinstance(c, dict)]
        self.contacts.sort(key=sort_key)
        self.template = _merge(DEFAULT_TEMPLATE, _read_json(self.dir / "vorlage.json", {}))
        self.settings = _merge(DEFAULT_SETTINGS, _read_json(self.dir / "einstellungen.json", {}))
        raw = _read_json(self.dir / "einsaetze.json", [])
        self.einsaetze = [e for e in raw if isinstance(e, dict) and e.get("id") and e.get("start")]
        self._sortiere_einsaetze()

    def ersteinrichtung(self):
        """Beim allerersten Start die Beispielvorlage (mit Muster-Logos) übernehmen."""
        beispiel = resource_dir() / BEISPIELVORLAGE
        if not (self.dir / "vorlage.json").exists() and beispiel.is_file():
            try:
                self.import_template(beispiel)
            except (OSError, ValueError):
                pass

    def save_contacts(self):
        self.contacts.sort(key=sort_key)
        _write_json(self.dir / "kontakte.json", self.contacts)

    def save_template(self):
        _write_json(self.dir / "vorlage.json", self.template)
        self._cleanup_assets()

    def save_settings(self):
        _write_json(self.dir / "einstellungen.json", self.settings)

    # ------------------------------------------------------------------ Gespeicherte Einsätze
    def _sortiere_einsaetze(self):
        self.einsaetze.sort(key=lambda e: (e.get("start", ""), e.get("nummer", "")), reverse=True)

    def save_einsaetze(self):
        self._sortiere_einsaetze()
        _write_json(self.dir / "einsaetze.json", self.einsaetze)

    def einsatz_by_id(self, eid: str) -> dict | None:
        return next((e for e in self.einsaetze if e["id"] == eid), None)

    def upsert_einsatz(self, einsatz: dict):
        self.einsaetze = [e for e in self.einsaetze if e["id"] != einsatz["id"]] + [einsatz]
        self.save_einsaetze()

    def delete_einsatz(self, eid: str):
        """Nur den Eintrag entfernen – die PDFs im Ablageordner bleiben erhalten."""
        self.einsaetze = [e for e in self.einsaetze if e["id"] != eid]
        self.save_einsaetze()

    # ------------------------------------------------------------------ Kontakte
    @staticmethod
    def _clean_contact(c: dict) -> dict:
        out = {"id": c.get("id") or uuid.uuid4().hex}
        for key in KONTAKT_FELDER:
            out[key] = str(c.get(key) or "").strip()
        return out

    def contact_by_id(self, cid: str) -> dict | None:
        return next((c for c in self.contacts if c["id"] == cid), None)

    def upsert_contact(self, contact: dict) -> dict:
        contact = self._clean_contact(contact)
        for i, c in enumerate(self.contacts):
            if c["id"] == contact["id"]:
                self.contacts[i] = contact
                break
        else:
            self.contacts.append(contact)
        self.save_contacts()
        return contact

    def delete_contact(self, cid: str):
        self.contacts = [c for c in self.contacts if c["id"] != cid]
        self.save_contacts()

    def add_contacts(self, new: list[dict]) -> tuple[int, int]:
        """Kontakte hinzufügen, Dubletten (gleiche E-Mail oder gleicher Name) überspringen."""
        emails = {c["email"].casefold() for c in self.contacts if c["email"]}
        names = {(c["vorname"].casefold(), c["nachname"].casefold()) for c in self.contacts}
        added = skipped = 0
        for raw in new:
            c = self._clean_contact(raw)
            key = (c["vorname"].casefold(), c["nachname"].casefold())
            if (c["email"] and c["email"].casefold() in emails) or key in names:
                skipped += 1
                continue
            self.contacts.append(c)
            emails.add(c["email"].casefold())
            names.add(key)
            added += 1
        self.save_contacts()
        return added, skipped

    # ------------------------------------------------------------------ Bilder
    def import_image(self, slot: str, source: Path) -> str:
        """Bild in den Datenordner kopieren und den neuen Dateinamen liefern."""
        data = Path(source).read_bytes()
        digest = hashlib.sha1(data).hexdigest()[:8]
        name = f"{slot}_{digest}{Path(source).suffix.lower() or '.png'}"
        (self.assets / name).write_bytes(data)
        return name

    def image_path(self, name: str) -> Path | None:
        if not name:
            return None
        path = self.assets / name
        return path if path.is_file() else None

    def _cleanup_assets(self):
        used = {self.template[f].get("datei") for f in BILD_FELDER}
        for file in self.assets.iterdir():
            if file.is_file() and file.name not in used:
                try:
                    file.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------ Vorlage teilen
    def export_template(self, target: Path):
        images = {}
        for slot in BILD_FELDER:
            path = self.image_path(self.template[slot].get("datei"))
            if path:
                images[path.name] = base64.b64encode(path.read_bytes()).decode("ascii")
        data = {"format": VORLAGE_FORMAT, "version": 1, "vorlage": self.template, "bilder": images}
        Path(target).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_template(self, source: Path):
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        if data.get("format") != VORLAGE_FORMAT:
            raise ValueError("Die Datei ist keine Vorlage dieser App.")
        for name, b64 in (data.get("bilder") or {}).items():
            safe = Path(name).name
            (self.assets / safe).write_bytes(base64.b64decode(b64))
        self.template = _merge(DEFAULT_TEMPLATE, data.get("vorlage") or {})
        for slot in BILD_FELDER:
            self.template[slot]["datei"] = Path(self.template[slot].get("datei") or "").name
        self.save_template()

    # ------------------------------------------------------------------ Einstellungen
    def output_dir(self) -> Path:
        configured = (self.settings.get("ausgabeordner") or "").strip()
        return Path(configured) if configured else documents_dir() / "Einsatzbescheinigungen"

    def bcc_list(self) -> list[str]:
        raw = self.settings.get("bcc") or ""
        return [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]
