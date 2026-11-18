"""Schnittstelle für die Browser-Version (Python im Browser per Pyodide).

Die Oberfläche (web/app.js) ruft über einen Web Worker ``aufruf(name, argumente_json)`` auf.
Argumente und Ergebnisse sind JSON; Dateien liegen im virtuellen Dateisystem und werden per Pfad
übergeben. Die Daten liegen im Datenordner (im Browser: /daten, gesichert im IndexedDB) – mit
denselben Dateien und Formaten wie in der Desktop-App. Erzeugt wird mit genau demselben Code.
"""

import base64
import json
import shutil
import tempfile
import traceback
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from . import __version__
from .formulare import (ABSCHNITTE, ANREDEN, BILD_MASSE, BILD_TITEL, DIENSTGRADE, EMAIL_RE,
                        KONTAKT_FORMULAR, TEXT_SCHLUESSEL, formular_aus_vorlage, vorlage_aus_formular)
from .generator import Einsatz, Teilnahme, einsatz_ordner, erzeuge, unknown_placeholders
from .generator import vorschau as _vorschau
from .importer import ZIELFELDER, auto_zuordnung, exportiere_csv, lese_tabelle, wende_an
from .mailer import Entwurf, schreibe_eml
from .pdfgen import SCHRIFTEN
from .placeholders import (PLATZHALTER_HILFE, combine, demo_context, fmt_date, fmt_duration,
                           fmt_time, parse_date, render, safe_filename)
from .storage import BILD_FELDER, DEFAULT_TEMPLATE, KONTAKT_FELDER, Store
from .verlauf import (anzeige_name, belegte_namen, eintragen, erstelle_sammel, finde,
                      kontakt_schluessel, lese_zeit, pdf_pfad, sammel_pfad, teilnehmer)

SICHERUNG_FORMAT = "einsatzbescheinigung-datensicherung"
SICHERUNG_MARKER = "datensicherung.json"
BILDTYPEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

TEMP_BEHALTEN = 40  # so viele temporäre Ordner (Downloads) bleiben erhalten

_store: Store | None = None
_temps: list[Path] = []


class Hinweis(Exception):
    """Meldung für den Nutzer (kein Programmfehler)."""


def _s() -> Store:
    if _store is None:
        raise RuntimeError("start() wurde noch nicht aufgerufen")
    return _store


def _ablage() -> Path:
    return _s().dir / "ablage"


def _temp(praefix: str) -> Path:
    """Temporärer Ordner für Downloads; ältere werden aufgeräumt (im Browser liegt /tmp im Speicher)."""
    ordner = Path(tempfile.mkdtemp(prefix=f"eb_{praefix}_"))
    _temps.append(ordner)
    while len(_temps) > TEMP_BEHALTEN:
        shutil.rmtree(_temps.pop(0), ignore_errors=True)
    return ordner


def _datum(text: str, was: str) -> date:
    try:
        return parse_date(text)
    except ValueError as err:
        raise Hinweis(f"{was}: {err}") from None


# ============================================================================ Start
def start() -> dict:
    """Daten laden (beim ersten Start die Beispielvorlage einrichten) und Grunddaten liefern."""
    global _store
    _store = Store()
    _store.ersteinrichtung()
    ctx, gender = demo_context()
    return {
        "version": __version__,
        "heute": fmt_date(date.today()),
        "kontakt_formular": KONTAKT_FORMULAR,
        "dienstgrade": DIENSTGRADE,
        "anreden": ANREDEN,
        "zielfelder": ZIELFELDER,
        "abschnitte": ABSCHNITTE,
        "bild_titel": BILD_TITEL,
        "bild_masse": BILD_MASSE,
        "schriften": SCHRIFTEN,
        "platzhalter": PLATZHALTER_HILFE,
        "standardtexte": {k: DEFAULT_TEMPLATE[k] for k in TEXT_SCHLUESSEL},
        "beispiel_dateiname": safe_filename(render(DEFAULT_TEMPLATE["dateiname"], ctx, gender)),
        "kontakte": kontakte(),
        "einstellungen": einstellungen(),
    }


# ============================================================================ Kontakte
def kontakte() -> list[dict]:
    return _s().contacts


def kontakt_speichern(werte: dict) -> dict:
    werte = {k: str(werte.get(k) or "").strip() for k in ["id", *KONTAKT_FELDER]}
    if werte["anrede"] == "keine Angabe":
        werte["anrede"] = ""
    if not werte["vorname"] and not werte["nachname"]:
        raise Hinweis("Bitte mindestens Vor- oder Nachnamen eingeben.")
    if werte["email"] and not EMAIL_RE.match(werte["email"]):
        raise Hinweis("Die E-Mail-Adresse sieht nicht gültig aus.")
    if not werte["id"]:
        del werte["id"]
    return _s().upsert_contact(werte)


def kontakt_loeschen(id: str) -> None:
    _s().delete_contact(id)


def tabelle_lesen(pfad: str) -> dict:
    try:
        kopf, zeilen = lese_tabelle(Path(pfad))
    except ValueError as err:
        raise Hinweis(str(err)) from None
    except Exception as err:  # noqa: BLE001 – z. B. defekte Excel-Datei
        raise Hinweis(f"Die Datei konnte nicht gelesen werden: {err}") from None
    return {"kopf": kopf, "zeilen": zeilen, "zuordnung": auto_zuordnung(kopf)}


def _zuordnung(kopf: list[str], zuordnung: dict) -> dict:
    out = {}
    for key, _ in ZIELFELDER:
        i = zuordnung.get(key)
        out[key] = i if isinstance(i, int) and 0 <= i < len(kopf) else None
    return out


def import_vorschau(kopf: list[str], zeilen: list[list[str]], zuordnung: dict) -> dict:
    neu = wende_an(kopf, zeilen, _zuordnung(kopf, zuordnung))
    return {"kontakte": neu[:8], "anzahl": len(neu), "ohne_mail": sum(1 for c in neu if not c["email"])}


def kontakte_importieren(kopf: list[str], zeilen: list[list[str]], zuordnung: dict) -> dict:
    neu = wende_an(kopf, zeilen, _zuordnung(kopf, zuordnung))
    if not neu:
        raise Hinweis("Es wurden keine Namen gefunden. Bitte die Zuordnung prüfen.")
    hinzu, uebersprungen = _s().add_contacts(neu)
    return {"neu": hinzu, "uebersprungen": uebersprungen}


def kontakte_exportieren() -> dict:
    if not _s().contacts:
        raise Hinweis("Es sind noch keine Kontakte vorhanden.")
    ziel = _temp("export") / "Kontakte.csv"
    exportiere_csv(_s().contacts, ziel)
    return {"pfad": str(ziel), "name": ziel.name}


# ============================================================================ Vorlage
def _bild(name: str) -> str | None:
    pfad = _s().image_path(name)
    if not pfad:
        return None
    typ = BILDTYPEN.get(pfad.suffix.lower(), "image/png")
    return f"data:{typ};base64,{base64.b64encode(pfad.read_bytes()).decode('ascii')}"


def _beispiel(muster: str) -> str:
    ctx, gender = demo_context()
    return safe_filename(render(muster or DEFAULT_TEMPLATE["dateiname"], ctx, gender)) + ".pdf"


def dateiname_beispiel(muster: str) -> str:
    return _beispiel(muster)


def vorlage() -> dict:
    tpl = _s().template
    return {"formular": formular_aus_vorlage(tpl), "schrift": tpl.get("schrift", "Arial Narrow"),
            "bilder": {slot: _bild(tpl[slot].get("datei")) for slot in BILD_FELDER}}


def _aus_formular(formular: dict, schrift: str) -> dict:
    try:
        tpl = vorlage_aus_formular(_s().template, formular)
    except ValueError as err:
        raise Hinweis(str(err)) from None
    tpl["schrift"] = schrift if schrift in SCHRIFTEN else "Arial Narrow"
    return tpl


def vorlage_pruefen(formular: dict, schrift: str) -> dict:
    tpl = _aus_formular(formular, schrift)
    return {"unbekannt": unknown_placeholders(tpl), "beispiel": _beispiel(tpl.get("dateiname"))}


def vorlage_speichern(formular: dict, schrift: str) -> dict:
    tpl = _aus_formular(formular, schrift)
    _s().template = tpl
    _s().save_template()
    return {"unbekannt": unknown_placeholders(tpl)}


def bild_uebernehmen(slot: str, pfad: str) -> dict:
    if slot not in BILD_FELDER:
        raise Hinweis("Unbekanntes Bildfeld.")
    quelle = Path(pfad)
    if quelle.suffix.lower() not in BILDTYPEN:
        raise Hinweis("Bitte ein Bild im Format PNG oder JPG wählen.")
    try:
        from PIL import Image

        with Image.open(quelle) as im:
            im.verify()
    except Exception:  # noqa: BLE001
        raise Hinweis("Die Datei ist kein lesbares Bild (PNG oder JPG).") from None
    name = _s().import_image(slot, quelle)
    return {"datei": name, "bild": _bild(name)}


def vorschau(formular: dict, schrift: str) -> dict:
    tpl = _aus_formular(formular, schrift)
    pfad = _vorschau(tpl, _s().assets)
    return {"pfad": str(pfad), "name": pfad.name, "unbekannt": unknown_placeholders(tpl)}


def vorlage_exportieren() -> dict:
    ziel = _temp("vorlage") / "Vorlage.einsatzvorlage"
    _s().export_template(ziel)
    return {"pfad": str(ziel), "name": ziel.name}


def vorlage_importieren(pfad: str) -> dict:
    try:
        _s().import_template(Path(pfad))
    except (ValueError, KeyError, TypeError) as err:
        raise Hinweis(f"Die Vorlage konnte nicht gelesen werden: {err}") from None
    return vorlage()


# ============================================================================ Einstellungen
def einstellungen() -> dict:
    s = _s().settings
    return {"bcc": s.get("bcc", ""), "mails_erstellen": bool(s.get("mails_erstellen", True)),
            "sammel_pdf": bool(s.get("sammel_pdf", True))}


def einstellungen_speichern(bcc: str, mails_erstellen: bool, sammel_pdf: bool) -> dict:
    s = _s()
    s.settings.update({"bcc": str(bcc or "").strip(), "mails_erstellen": bool(mails_erstellen),
                       "sammel_pdf": bool(sammel_pdf)})
    s.save_settings()
    return {"falsch": [a for a in s.bcc_list() if not EMAIL_RE.match(a)]}


# ============================================================================ Einsatz
def _einsatzzeit(sd: str, st: str, ed: str, et: str) -> tuple[datetime, datetime, bool]:
    """Wie in der Desktop-App: Ende ≤ Beginn am selben Datum → Ende am Folgetag."""
    start, end = combine(sd, st), combine(ed, et)
    folgetag = False
    if end <= start and ed.strip() == sd.strip():
        end += timedelta(days=1)
        folgetag = True
    return start, end, folgetag


def _erstellt_am(t: dict) -> str:
    try:
        return datetime.fromisoformat(t.get("erstellt", "")).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def _treffer(nummer: str, sd: str, st: str) -> dict | None:
    try:
        return finde(_s().einsaetze, nummer, combine(sd, st))
    except ValueError:
        return None


def _zeiten(start: datetime, end: datetime) -> dict:
    return {"sd": fmt_date(start), "st": fmt_time(start), "ed": fmt_date(end), "et": fmt_time(end)}


def einsatz_pruefen(nummer: str, sd: str, st: str, ed: str, et: str) -> dict:
    """Live-Hinweise auf Seite 1: Dauer, Fehler und ob der Einsatz schon gespeichert ist."""
    out = {"dauer": "", "fehler": "", "treffer": None}
    try:
        start, end, folgetag = _einsatzzeit(sd, st, ed, et)
        if end <= start:
            out["fehler"] = "Ende liegt vor dem Beginn"
        else:
            out["dauer"] = f"Dauer: {fmt_duration(end - start)}" + (" · Ende am Folgetag" if folgetag else "")
    except ValueError:
        pass
    rec = _treffer(nummer, sd, st)
    if rec:
        out["treffer"] = {"id": rec["id"], "anzahl": len(rec.get("teilnehmer", [])),
                          "status": {k: f"✓ erstellt am {_erstellt_am(t)}" for k, t in teilnehmer(rec).items()}}
    return out


def weiter(nummer: str, sd: str, st: str, ed: str, et: str, ausst: str, auswahl: list[str]) -> dict:
    """Schritt 1 → 2: prüfen und die Zeilen je Kamerad vorbereiten."""
    try:
        start, end, folgetag = _einsatzzeit(sd, st, ed, et)
    except ValueError as err:
        raise Hinweis(str(err)) from None
    _datum(ausst, "Ausstellungsdatum")
    if end <= start:
        raise Hinweis("Das Einsatzende liegt vor dem Beginn.")
    kontakte = [c for c in _s().contacts if c["id"] in set(auswahl)]
    if not kontakte:
        raise Hinweis("Bitte mindestens einen Kameraden auswählen.")
    fragen = []
    if end - start > timedelta(hours=24):
        fragen.append(f"Der Einsatz dauert {fmt_duration(end - start)}. Ist das richtig?")
    if not nummer.strip():
        fragen.append("Es ist keine Einsatznummer eingetragen. Trotzdem fortfahren?")

    rec = finde(_s().einsaetze, nummer, start)
    fertig = teilnehmer(rec)
    zeilen = []
    for c in kontakte:
        t = fertig.get(c["id"])
        hinweise = ([] if c["email"] else ["keine E-Mail"]) + (["wird neu erstellt"] if t else [])
        zeilen.append({
            "id": c["id"],
            "name": anzeige_name(c) + (f"  ({c['dienstgrad']})" if c["dienstgrad"] else ""),
            "email": c["email"], "hinweis": " · ".join(hinweise),
            "gespeichert": _zeiten(lese_zeit(t["start"]), lese_zeit(t["ende"])) if t else None,
        })
    ende_text = fmt_time(end) if start.date() == end.date() else f"{fmt_date(end)} {fmt_time(end)}"
    teile = [f"Einsatz {nummer.strip()}" if nummer.strip() else "Einsatz ohne Nummer",
             f"{fmt_date(start)} {fmt_time(start)} – {ende_text} Uhr",
             f"{len(kontakte)} Kamerad{'en' if len(kontakte) != 1 else ''}"]
    if rec:
        teile.append(f"Ergänzung – {len(fertig)} bereits bescheinigt")
    return {
        "fragen": fragen,
        "ende_datum": fmt_date(end) if folgetag else None,
        "schluessel": [_zeiten(start, end), rec["id"] if rec else None],
        "standard": _zeiten(start, end),
        "kopf": "  ·  ".join(teile),
        "ergaenzung": rec is not None,
        "zeilen": zeilen,
        "bcc": _s().bcc_list(),
    }


def _zeile(standard: dict, werte: dict) -> dict:
    try:
        s, e = combine(werte["sd"], werte["st"]), combine(werte["ed"], werte["et"])
    except (ValueError, KeyError):
        return {"text": "ungültige Eingabe", "art": "fehler"}
    if e <= s:
        return {"text": "Ende vor Beginn", "art": "fehler"}
    angepasst = {k: werte.get(k) for k in standard} != standard
    return {"text": fmt_duration(e - s) + ("  · angepasst" if angepasst else ""),
            "art": "info" if angepasst else ""}


def zeilen_pruefen(standard: dict, zeilen: dict) -> dict:
    return {cid: _zeile(standard, w) for cid, w in zeilen.items()}


def _teilnahmen(zeilen: list[dict]) -> tuple[list[Teilnahme], list[str]]:
    teilnahmen, fehler = [], []
    for z in zeilen:
        c = _s().contact_by_id(z.get("id", ""))
        if not c:
            continue
        try:
            s, e = combine(z["sd"], z["st"]), combine(z["ed"], z["et"])
        except (ValueError, KeyError) as err:
            fehler.append(f"{anzeige_name(c)}: {err}")
            continue
        if e <= s:
            fehler.append(f"{anzeige_name(c)}: Das Ende liegt nicht nach dem Beginn.")
            continue
        teilnahmen.append(Teilnahme(c, s, e))
    return teilnahmen, fehler


def erstellen_pruefen(zeilen: list[dict], mails: bool) -> dict:
    """Vor dem Erstellen: Fehler (blockierend) und Rückfragen (bestätigen lassen)."""
    teilnahmen, fehler = _teilnahmen(zeilen)
    if fehler:
        raise Hinweis("Bitte Zeiten prüfen:\n" + "\n".join(fehler))
    fragen = []
    unbekannt = unknown_placeholders(_s().template)
    if unbekannt:
        fragen.append("Die Vorlage enthält Platzhalter, die nicht ersetzt werden können:\n\n"
                      + ", ".join(unbekannt) + "\n\nTrotzdem fortfahren?")
    ohne = [anzeige_name(t.contact) for t in teilnahmen if not t.contact["email"]]
    if mails and ohne:
        fragen.append("Für folgende Kameraden ist keine E-Mail-Adresse hinterlegt:\n\n• " + "\n• ".join(ohne)
                      + "\n\nDie PDFs werden trotzdem erstellt, es gibt aber keinen E-Mail-Entwurf. Fortfahren?")
    return {"fragen": fragen}


def _mailto(an: str, betreff: str, text: str, bcc: list[str]) -> str:
    teile = [f"subject={quote(betreff, safe='')}", f"body={quote(text.replace(chr(10), chr(13) + chr(10)), safe='')}"]
    if bcc:
        teile.append(f"bcc={quote(','.join(bcc), safe='@,')}")
    return f"mailto:{quote(an, safe='@')}?" + "&".join(teile)


def _zip(ziel: Path, dateien: list[Path]) -> Path:
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for d in dateien:
            z.write(d, d.name)
    return ziel


def erstellen(nummer: str, sd: str, st: str, ed: str, et: str, ausst: str, zeilen: list[dict],
              mails: bool, sammel: bool) -> dict:
    """PDFs erzeugen, Einsatz speichern, Sammel-PDF aktualisieren und E-Mail-Entwürfe (.eml) anlegen."""
    s = _s()
    try:
        start, end, _ = _einsatzzeit(sd, st, ed, et)
    except ValueError as err:
        raise Hinweis(str(err)) from None
    einsatz = Einsatz(nummer.strip(), start, end, _datum(ausst, "Ausstellungsdatum"))
    teilnahmen, fehler = _teilnahmen(zeilen)
    if fehler:
        raise Hinweis("Bitte Zeiten prüfen:\n" + "\n".join(fehler))
    if not teilnahmen:
        raise Hinweis("Bitte mindestens einen Kameraden auswählen.")

    rec = finde(s.einsaetze, einsatz.nummer, start)
    ordner = (Path(rec["ordner"]) if rec and Path(rec.get("ordner", "")).is_dir()
              else einsatz_ordner(_ablage(), Einsatz(einsatz.nummer, start, start, date.today())))
    neu = {kontakt_schluessel(t.contact) for t in teilnahmen}
    ergebnisse, ordner = erzeuge(einsatz, teilnahmen, s.template, s.assets, ordner,
                                 belegte_namen(rec, neu), use_system_fonts=False)
    ergaenzt = rec is not None
    rec = eintragen(rec, einsatz, ergebnisse, ordner)
    s.upsert_einsatz(rec)

    hinweise, sammel_pdf = [], None
    if sammel:
        try:
            sammel_pdf, fehlen = erstelle_sammel(rec)
            if fehlen:
                hinweise.append("Nicht im Sammel-PDF, weil die Datei fehlt: " + ", ".join(fehlen))
        except Exception as err:  # noqa: BLE001
            hinweise.append(f"Sammel-PDF fehlgeschlagen: {err}")

    entwuerfe = _temp("entwuerfe")
    bcc = s.bcc_list()
    paket, ergebnis_zeilen = [], []
    for erg in ergebnisse:
        zeile = {"name": anzeige_name(erg.contact), "ok": True, "info": "PDF erstellt",
                 "email": erg.contact["email"], "betreff": erg.betreff, "text": erg.text,
                 "pdf": str(erg.pdf), "pdf_name": erg.pdf.name, "eml": None, "mailto": None}
        paket.append(erg.pdf)
        if mails and erg.contact["email"]:
            eml = schreibe_eml(Entwurf(erg.contact["email"], erg.betreff, erg.text, [erg.pdf], bcc), entwuerfe)
            zeile.update(eml=str(eml), eml_name=eml.name, info="PDF und E-Mail-Entwurf erstellt",
                         mailto=_mailto(erg.contact["email"], erg.betreff, erg.text, bcc))
            paket.append(eml)
        elif mails:
            zeile.update(ok=False, info="PDF erstellt · kein Entwurf (keine E-Mail-Adresse)")
        ergebnis_zeilen.append(zeile)
    if sammel_pdf:
        paket.append(sammel_pdf)
    zip_name = ordner.name + ("_Ergaenzung" if ergaenzt else "") + ".zip"
    zip_pfad = _zip(_temp("zip") / zip_name, paket)

    n = len(ergebnisse)
    titel = f"{n} Bescheinigung{'en' if n != 1 else ''} erstellt"
    if ergaenzt:
        titel += f" – der Einsatz hat jetzt {len(rec['teilnehmer'])} Bescheinigungen"
    return {
        "titel": titel, "zeilen": sorted(ergebnis_zeilen, key=lambda z: z["name"].casefold()),
        "hinweise": hinweise, "einsatz_id": rec["id"], "ergaenzt": ergaenzt, "gesamt": len(rec["teilnehmer"]),
        "sammel": str(sammel_pdf) if sammel_pdf else None, "sammel_name": sammel_pdf.name if sammel_pdf else None,
        "zip": str(zip_pfad), "zip_name": zip_name, "mails": bool(mails), "bcc": bcc,
    }


# ============================================================================ Gespeicherte Einsätze
def _zeitraum(start: datetime, end: datetime) -> str:
    ende = fmt_time(end) if start.date() == end.date() else f"{fmt_date(end)} {fmt_time(end)}"
    return f"{fmt_time(start)} – {ende}"


def _zeitstempel(text: str) -> str:
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


def _rec(id: str) -> dict:
    rec = _s().einsatz_by_id(id)
    if not rec:
        raise Hinweis("Dieser Einsatz ist nicht mehr gespeichert.")
    return rec


def einsaetze(filter: str = "") -> list[dict]:
    filt = filter.strip().casefold()
    out = []
    for rec in _s().einsaetze:
        start, end = lese_zeit(rec["start"]), lese_zeit(rec["ende"])
        namen = " ".join(anzeige_name(t["kontakt"]) for t in rec.get("teilnehmer", []))
        if filt and filt not in f"{rec.get('nummer', '')} {fmt_date(start)} {namen}".casefold():
            continue
        out.append({"id": rec["id"], "datum": fmt_date(start), "zeit": _zeitraum(start, end),
                    "nummer": rec.get("nummer") or "– ohne Nummer –",
                    "anzahl": len(rec.get("teilnehmer", [])), "geaendert": _zeitstempel(rec.get("geaendert"))})
    return out


def einsatz_details(id: str) -> dict:
    rec = _rec(id)
    out = []
    for t in rec.get("teilnehmer", []):
        s, e = lese_zeit(t["start"]), lese_zeit(t["ende"])
        out.append({"name": anzeige_name(t["kontakt"]), "dienstgrad": t["kontakt"].get("dienstgrad", ""),
                    "zeit": f"{fmt_date(s)}  {_zeitraum(s, e)}", "erstellt": _zeitstempel(t.get("erstellt")),
                    "vorhanden": pdf_pfad(rec, t).is_file()})
    return {"teilnehmer": out, "sammel": sammel_pfad(rec).is_file()}


def einsatz_laden(id: str) -> dict:
    rec = _rec(id)
    start, end = lese_zeit(rec["start"]), lese_zeit(rec["ende"])
    return {"nummer": rec.get("nummer", ""), **_zeiten(start, end), "ausst": fmt_date(date.today())}


def einsatz_paket(id: str) -> dict:
    """Alle vorhandenen PDFs eines Einsatzes (samt Sammel-PDF) als ZIP."""
    rec = _rec(id)
    dateien = [pdf_pfad(rec, t) for t in rec.get("teilnehmer", []) if pdf_pfad(rec, t).is_file()]
    if sammel_pfad(rec).is_file():
        dateien.append(sammel_pfad(rec))
    if not dateien:
        raise Hinweis("Zu diesem Einsatz sind keine PDFs mehr gespeichert.")
    name = Path(rec["ordner"]).name + ".zip"
    return {"pfad": str(_zip(_temp("zip") / name, dateien)), "name": name}


def einsatz_sammel(id: str) -> dict:
    rec = _rec(id)
    pfad, fehlen = erstelle_sammel(rec)
    if not pfad:
        raise Hinweis("Zu diesem Einsatz sind keine PDFs mehr gespeichert.")
    return {"pfad": str(pfad), "name": pfad.name, "fehlen": fehlen}


def einsatz_entfernen(id: str) -> None:
    """Eintrag entfernen und – anders als am Desktop – auch die PDFs im Browser-Speicher."""
    rec = _rec(id)
    ordner = Path(rec.get("ordner", ""))
    _s().delete_einsatz(id)
    if ordner.is_dir() and _ablage() in ordner.parents:
        shutil.rmtree(ordner, ignore_errors=True)


# ============================================================================ Datensicherung
def _sicherbare_dateien() -> list[Path]:
    basis = _s().dir
    return sorted(p for p in basis.rglob("*") if p.is_file() and not p.name.endswith((".tmp", ".bak")))


def speicherbedarf() -> dict:
    dateien = _sicherbare_dateien()
    return {"bytes": sum(p.stat().st_size for p in dateien), "dateien": len(dateien),
            "kontakte": len(_s().contacts), "einsaetze": len(_s().einsaetze)}


def datensicherung() -> dict:
    basis = _s().dir
    name = f"Einsatzbescheinigung_Datensicherung_{date.today():%Y-%m-%d}.zip"
    ziel = _temp("sicherung") / name
    marker = {"format": SICHERUNG_FORMAT, "version": 1, "app": __version__,
              "erstellt": datetime.now().isoformat(timespec="seconds")}
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(SICHERUNG_MARKER, json.dumps(marker, ensure_ascii=False, indent=2))
        for p in _sicherbare_dateien():
            z.write(p, p.relative_to(basis).as_posix())
    return {"pfad": str(ziel), "name": name}


def datensicherung_laden(pfad: str) -> dict:
    """Alle Daten durch die Sicherung ersetzen."""
    global _store
    try:
        z = zipfile.ZipFile(pfad)
    except zipfile.BadZipFile:
        raise Hinweis("Die Datei ist keine Datensicherung dieser App.") from None
    with z:
        try:
            marker = json.loads(z.read(SICHERUNG_MARKER))
        except (KeyError, ValueError):
            raise Hinweis("Die Datei ist keine Datensicherung dieser App.") from None
        if marker.get("format") != SICHERUNG_FORMAT:
            raise Hinweis("Die Datei ist keine Datensicherung dieser App.")
        eintraege = []
        for info in z.infolist():
            teile = PurePosixPath(info.filename).parts
            if info.is_dir() or info.filename == SICHERUNG_MARKER:
                continue
            if not teile or info.filename.startswith("/") or ".." in teile or "\\" in info.filename:
                raise Hinweis("Die Datensicherung enthält ungültige Pfade.")
            eintraege.append(info)
        basis = _s().dir
        for kind in list(basis.iterdir()):
            shutil.rmtree(kind) if kind.is_dir() else kind.unlink()
        for info in eintraege:
            ziel = basis.joinpath(*PurePosixPath(info.filename).parts)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(z.read(info))
    _store = Store(basis)
    return {"kontakte": kontakte(), "einstellungen": einstellungen(), "erstellt": marker.get("erstellt", "")}


# ============================================================================ Lizenzen
def lizenzen() -> str:
    from .lizenzinfo import text

    return text()


# ============================================================================ Aufruf aus dem Browser
_API = {f.__name__: f for f in (
    start, kontakte, kontakt_speichern, kontakt_loeschen, tabelle_lesen, import_vorschau,
    kontakte_importieren, kontakte_exportieren, dateiname_beispiel, vorlage, vorlage_pruefen, vorlage_speichern,
    bild_uebernehmen, vorschau, vorlage_exportieren, vorlage_importieren, einstellungen,
    einstellungen_speichern, einsatz_pruefen, weiter, zeilen_pruefen, erstellen_pruefen, erstellen,
    einsaetze, einsatz_details, einsatz_laden, einsatz_paket, einsatz_sammel, einsatz_entfernen,
    speicherbedarf, datensicherung, datensicherung_laden, lizenzen)}


def aufruf(name: str, argumente: str = "{}") -> str:
    """Einziger Einstieg für den Browser: Funktion per Name, Argumente/Ergebnis als JSON."""
    fn = _API.get(name)
    if fn is None:
        return json.dumps({"ok": False, "fehler": f"Unbekannte Funktion: {name}"})
    try:
        wert = fn(**json.loads(argumente or "{}"))
        return json.dumps({"ok": True, "wert": wert}, ensure_ascii=False)
    except Hinweis as h:
        return json.dumps({"ok": False, "meldung": str(h)}, ensure_ascii=False)
    except Exception:  # noqa: BLE001 – Programmfehler mit Details anzeigen
        return json.dumps({"ok": False, "fehler": traceback.format_exc()}, ensure_ascii=False)
