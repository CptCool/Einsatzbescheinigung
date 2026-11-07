"""Gespeicherte Einsätze: wer wann für welchen Einsatz eine Bescheinigung bekommen hat.

Damit lassen sich vergessene Kameraden nachträglich ergänzen. Die neuen PDFs landen im selben
Ordner, und das Sammel-PDF wird aus allen Einzel-PDFs des Einsatzes neu zusammengesetzt.
Ein Einsatz ist eindeutig durch Einsatznummer + Beginn (Datum und Uhrzeit) bestimmt – genau
daraus entsteht auch der Name des Ablageordners.
"""

import uuid
from datetime import datetime
from pathlib import Path

from .generator import Einsatz, Ergebnis, fuege_zusammen, sammel_dateiname
from .storage import KONTAKT_FELDER, sort_key

ZEITFORMAT = "%Y-%m-%dT%H:%M"


def zeit(dt: datetime) -> str:
    return dt.strftime(ZEITFORMAT)


def lese_zeit(text: str) -> datetime:
    return datetime.strptime(text, ZEITFORMAT)


def anzeige_name(kontakt: dict) -> str:
    name = f"{kontakt.get('nachname', '')}, {kontakt.get('vorname', '')}".strip(", ")
    return name or "(ohne Namen)"


def kontakt_schluessel(kontakt: dict) -> str:
    return kontakt.get("id") or f"{kontakt.get('vorname', '')}|{kontakt.get('nachname', '')}".casefold()


def finde(einsaetze: list[dict], nummer: str, start: datetime) -> dict | None:
    """Gespeicherten Einsatz mit gleicher Nummer und gleichem Beginn suchen."""
    key = (nummer.strip(), zeit(start))
    return next((e for e in einsaetze if (e.get("nummer", "").strip(), e.get("start")) == key), None)


def teilnehmer(rec: dict | None) -> dict[str, dict]:
    """Bereits bescheinigte Kameraden eines Einsatzes, nach Kontakt-ID."""
    return {t["kontakt_id"]: t for t in (rec or {}).get("teilnehmer", [])}


def belegte_namen(rec: dict | None, neu_erstellt: set[str]) -> set[str]:
    """PDF-Namen anderer Kameraden, die beim Ergänzen nicht überschrieben werden dürfen."""
    return {Path(t["pdf"]).stem for k, t in teilnehmer(rec).items() if k not in neu_erstellt}


def eintragen(rec: dict | None, einsatz: Einsatz, ergebnisse: list[Ergebnis], ordner: Path) -> dict:
    """Neue (oder neu erstellte) Bescheinigungen in den gespeicherten Einsatz übernehmen."""
    jetzt = datetime.now().isoformat(timespec="seconds")
    rec = dict(rec) if rec else {"id": uuid.uuid4().hex, "erstellt": jetzt}
    rec.update({"nummer": einsatz.nummer.strip(), "start": zeit(einsatz.start),
                "ende": zeit(einsatz.end), "ordner": str(ordner), "geaendert": jetzt})
    alle = teilnehmer(rec)
    for erg in ergebnisse:
        kid = kontakt_schluessel(erg.contact)
        alle[kid] = {
            "kontakt_id": kid,
            # Kopie der Kontaktdaten zum Zeitpunkt der Bescheinigung
            "kontakt": {k: str(erg.contact.get(k) or "") for k in KONTAKT_FELDER},
            "start": zeit(erg.start),
            "ende": zeit(erg.end),
            "pdf": erg.pdf.name,
            "ausstellungsdatum": einsatz.ausstellungsdatum.isoformat(),
            "erstellt": jetzt,
        }
    rec["teilnehmer"] = sorted(alle.values(), key=lambda t: sort_key(t["kontakt"]))
    return rec


def pdf_pfad(rec: dict, t: dict) -> Path:
    return Path(rec["ordner"]) / t["pdf"]


def sammel_pfad(rec: dict) -> Path:
    return Path(rec["ordner"]) / sammel_dateiname(rec.get("nummer", ""), lese_zeit(rec["start"]))


def erstelle_sammel(rec: dict) -> tuple[Path | None, list[str]]:
    """Sammel-PDF aus allen vorhandenen Einzel-PDFs. Liefert (Pfad, Namen mit fehlender Datei)."""
    vorhanden, fehlen = [], []
    for t in rec.get("teilnehmer", []):
        pfad = pdf_pfad(rec, t)
        if pfad.is_file():
            vorhanden.append(pfad)
        else:
            fehlen.append(anzeige_name(t["kontakt"]))
    if not vorhanden:
        return None, fehlen
    return fuege_zusammen(vorhanden, sammel_pfad(rec)), fehlen
