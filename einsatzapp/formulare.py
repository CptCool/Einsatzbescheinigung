"""Felder, Auswahllisten und Prüfungen der Formulare – gemeinsam für Desktop- und Browser-Version."""

import copy
import math
import re

from .storage import BILD_FELDER

# ---------------------------------------------------------------------------- Kontakte
DIENSTGRADE = ["FMA", "FFA", "FM", "FF", "OFM", "OFF", "HFM", "HFF", "UBM", "BM", "OBM", "HBM",
               "BI", "BOI", "BAM"]
ANREDEN = ["Herr", "Frau", "keine Angabe"]
KONTAKT_FORMULAR = [("anrede", "Anrede"), ("dienstgrad", "Dienstgrad"), ("vorname", "Vorname"),
                    ("nachname", "Nachname"), ("strasse", "Straße und Hausnummer"), ("plz", "PLZ"),
                    ("ort", "Ort"), ("email", "E-Mail")]
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

# ---------------------------------------------------------------------------- Vorlage
BILD_TITEL = {"logo_links": "Logo links", "logo_rechts": "Logo rechts", "unterschrift": "Unterschrift"}
BILD_MASSE = {
    "logo_links": [("x", "X"), ("y", "Y"), ("b", "Breite"), ("h", "Höhe (0 = autom.)")],
    "logo_rechts": [("x", "X"), ("y", "Y"), ("b", "Breite"), ("h", "Höhe (0 = autom.)")],
    "unterschrift": [("x", "X"), ("b", "Breite"), ("dy", "Versatz nach unten")],
}

# (Schlüssel, Beschriftung, Art, Höhe, Hinweis)
ABSCHNITTE = [
    ("Briefkopf", [
        ("logo_links", None, "bild", 0, ""),
        ("logo_rechts", None, "bild", 0, ""),
        ("kopf_text", "Text unter dem rechten Logo", "entry", 0, ""),
        ("schrift", "Schriftart", "schrift", 0,
         "Arial Narrow wie im Original. Fehlt sie auf dem Rechner, wird die maßgleiche "
         "„Liberation Sans Narrow“ verwendet."),
    ]),
    ("Anschrift und Infoblock", [
        ("anschrift", "Anschrift", "text", 5, "Leere Zeilen (z. B. ohne Straße) werden weggelassen."),
        ("infoblock", "Infoblock rechts", "text", 8, "Pro Zeile: Bezeichnung | Wert"),
        ("datum_bezeichnung", "Datum – Bezeichnung", "entry", 0, ""),
        ("datum_wert", "Datum – Wert", "entry", 0, ""),
    ]),
    ("Brieftext", [
        ("titel", "Überschrift", "entry", 0, ""),
        ("anrede", "Anrede", "entry", 0, ""),
        ("text", "Text", "text", 7, "Zeilenumbruch = neuer Absatz ohne Leerzeile; "
                                    "Leerzeile = Absatz mit Abstand."),
        ("gruss", "Grußformel", "text", 2, ""),
    ]),
    ("Unterschrift", [
        ("unterschrift", None, "bild", 0, ""),
        ("unterzeichner", "Unterzeichner", "text", 3, ""),
    ]),
    ("E-Mail", [
        ("mail_betreff", "Betreff", "entry", 0, ""),
        ("mail_text", "Text", "text", 10, "Der PDF-Anhang wird automatisch angefügt."),
    ]),
    ("Dateiname", [
        ("dateiname", "Dateiname (ohne .pdf)", "entry", 0, ""),
    ]),
]
TEXT_SCHLUESSEL = [key for _, felder in ABSCHNITTE for key, _l, art, _h, _t in felder if art != "bild"]


def zahl_text(wert) -> str:
    """Maß für das Formular: 25.3 → „25,3“."""
    return f"{wert:g}".replace(".", ",") if isinstance(wert, (int, float)) else str(wert or "")


def formular_aus_vorlage(template: dict) -> dict:
    """Vorlage als Formularwerte (Texte unverändert, Maße als Text mit Komma)."""
    roh = {key: template.get(key, "") for key in TEXT_SCHLUESSEL}
    for slot in BILD_FELDER:
        spec = template.get(slot) or {}
        roh[slot] = {"datei": spec.get("datei", "")}
        for key, _label in BILD_MASSE[slot]:
            roh[slot][key] = zahl_text(spec.get(key, ""))
    return roh


def vorlage_aus_formular(template: dict, roh: dict) -> dict:
    """Formularwerte in die Vorlage übernehmen; wirft ValueError bei ungültigen Maßen."""
    tpl = copy.deepcopy(template)
    for key in TEXT_SCHLUESSEL:
        if key in roh:
            tpl[key] = str(roh[key])
    for slot in BILD_FELDER:
        werte = roh.get(slot) or {}
        spec = {"datei": str(werte.get("datei") or "")}
        for key, label in BILD_MASSE[slot]:
            text = str(werte.get(key, "")).strip().replace(",", ".") or "0"
            try:
                zahl = float(text)
                if not math.isfinite(zahl):
                    raise ValueError
            except ValueError:
                raise ValueError(f"{BILD_TITEL[slot]}: „{werte.get(key)}“ ist keine Zahl ({label}).") from None
            spec[key] = round(zahl, 2)
        tpl[slot] = spec
    return tpl
