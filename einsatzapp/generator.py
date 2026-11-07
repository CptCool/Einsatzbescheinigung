"""Bescheinigungen für einen Einsatz erzeugen (Einzel-PDFs) und zum Sammel-PDF zusammenfügen."""

import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .pdfgen import Renderer
from .placeholders import build_context, demo_context, gender_index, render, safe_filename
from .storage import DEFAULT_TEMPLATE

TEXT_FELDER = [k for k, v in DEFAULT_TEMPLATE.items() if isinstance(v, str) and k != "schrift"]


@dataclass
class Einsatz:
    nummer: str
    start: datetime
    end: datetime
    ausstellungsdatum: date


@dataclass
class Teilnahme:
    contact: dict
    start: datetime
    end: datetime


@dataclass
class Ergebnis:
    contact: dict
    pdf: Path
    betreff: str
    text: str
    start: datetime
    end: datetime


def unknown_placeholders(template: dict) -> list[str]:
    """Platzhalter in der Vorlage, die die App nicht kennt (Tippfehler)."""
    ctx, gender = demo_context()
    unknown: set = set()
    for key in TEXT_FELDER:
        render(template.get(key, ""), ctx, gender, unknown)
    return sorted(unknown)


def einsatz_ordner(base: Path, einsatz: Einsatz) -> Path:
    name = f"{einsatz.start:%Y-%m-%d}_{einsatz.start:%H%M}_Einsatz"
    if einsatz.nummer.strip():
        name += f"_{einsatz.nummer.strip()}"
    return Path(base) / safe_filename(name)


def sammel_dateiname(nummer: str, start: datetime) -> str:
    nr = f"_Einsatz_{nummer.strip()}" if nummer.strip() else "_Einsatz"
    return safe_filename(f"{start:%Y-%m-%d}_{start:%H%M}{nr}_Alle_Bescheinigungen") + ".pdf"


def erzeuge(einsatz: Einsatz, teilnahmen: list[Teilnahme], template: dict, assets_dir: Path,
            ordner: Path, belegt=(), use_system_fonts: bool = True):
    """Erzeugt je Teilnahme ein PDF in ``ordner``. Liefert (Ergebnisse, Ordner).

    ``belegt``: Dateinamen (ohne .pdf) anderer Kameraden, die schon im Ordner liegen und nicht
    überschrieben werden dürfen – wichtig beim nachträglichen Ergänzen eines Einsatzes.
    """
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    ergebnisse: list[Ergebnis] = []
    used_names: set[str] = {n.casefold() for n in belegt}

    for t in teilnahmen:
        ctx = build_context(t.contact, einsatz.nummer, einsatz.start, einsatz.end,
                            t.start, t.end, einsatz.ausstellungsdatum)
        gender = gender_index(t.contact.get("anrede"))

        stem = safe_filename(render(template.get("dateiname") or DEFAULT_TEMPLATE["dateiname"],
                                    ctx, gender))
        name, n = stem, 2
        while name.casefold() in used_names:
            name, n = f"{stem}_{n}", n + 1
        used_names.add(name.casefold())

        single = Renderer(template, assets_dir, use_system_fonts)
        single.add_page(ctx, gender)
        pdf_path = ordner / f"{name}.pdf"
        single.save(pdf_path, title=f"Einsatzbescheinigung {ctx['Name']}")

        betreff = " ".join(render(template.get("mail_betreff", ""), ctx, gender).split())
        text = render(template.get("mail_text", ""), ctx, gender)
        ergebnisse.append(Ergebnis(t.contact, pdf_path, betreff, text, t.start, t.end))
    return ergebnisse, ordner


def fuege_zusammen(pdfs: list[Path], ziel: Path) -> Path:
    """Einzel-PDFs unverändert zu einem Sammel-PDF zusammenfügen (identisch mit dem Versand)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for pdf in pdfs:
        writer.append(str(pdf), import_outline=False)
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    writer.add_metadata({"/Title": "Einsatzbescheinigungen (Sammel-PDF)",
                         "/Producer": "Einsatzbescheinigung"})
    ziel = Path(ziel)
    tmp = ziel.with_name(ziel.name + ".tmp")
    with open(tmp, "wb") as f:
        writer.write(f)
    try:
        os.replace(tmp, ziel)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return ziel


def vorschau(template: dict, assets_dir: Path, contact: dict | None = None) -> Path:
    """Beispiel-PDF in einen temporären Ordner schreiben und den Pfad liefern."""
    ctx, gender = demo_context()
    if contact:
        start, end = datetime(2026, 4, 7, 11, 59), datetime(2026, 4, 7, 15, 0)
        ctx = build_context(contact, "2026-117", start, end, start, end, date.today())
        gender = gender_index(contact.get("anrede"))
    r = Renderer(template, assets_dir)
    r.add_page(ctx, gender)
    out = Path(tempfile.mkdtemp(prefix="einsatzbescheinigung_")) / "Vorschau_Einsatzbescheinigung.pdf"
    r.save(out, title="Vorschau Einsatzbescheinigung")
    return out
