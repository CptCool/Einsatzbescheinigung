"""Tests ohne Oberfläche: Platzhalter, Parser, PDF, gespeicherte Einsätze, Import, .eml.

Start: python -m unittest discover -s tests -t .
"""

import copy
import email
import email.policy
import os
import re
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("EINSATZBESCHEINIGUNG_DATEN", tempfile.mkdtemp(prefix="eb_test_"))

from einsatzapp.generator import (Einsatz, Teilnahme, einsatz_ordner, erzeuge,  # noqa: E402
                                  unknown_placeholders)
from einsatzapp.importer import auto_zuordnung, lese_tabelle, wende_an  # noqa: E402
from einsatzapp.mailer import Entwurf, schreibe_eml  # noqa: E402
from einsatzapp.pdfgen import resolve_fonts  # noqa: E402
from einsatzapp.placeholders import (build_context, demo_context, gender_index,  # noqa: E402
                                     parse_date, parse_time, render, safe_filename)
from einsatzapp.paths import resource_dir  # noqa: E402
from einsatzapp.pdfgen import Renderer  # noqa: E402
from einsatzapp.storage import BEISPIELVORLAGE, BILD_FELDER, DEFAULT_TEMPLATE, Store  # noqa: E402
from einsatzapp.verlauf import (belegte_namen, eintragen, erstelle_sammel, finde,  # noqa: E402
                                kontakt_schluessel, teilnehmer)

MAX = {"id": "k-max", "anrede": "Herr", "vorname": "Max", "nachname": "Mustermann", "dienstgrad": "OFM",
       "strasse": "Musterweg 1", "plz": "12345", "ort": "Musterstadt", "email": "max@example.org"}
ANNA = {"id": "k-anna", "anrede": "Frau", "vorname": "Anna", "nachname": "Müller", "dienstgrad": "HFF",
        "strasse": "", "plz": "12345", "ort": "Musterstadt", "email": ""}
ERIKA = {"id": "k-erika", "anrede": "Frau", "vorname": "Erika", "nachname": "Musterfrau",
         "dienstgrad": "BM", "strasse": "Feldweg 2", "plz": "12345", "ort": "Musterstadt",
         "email": "erika@example.org"}


def seiten(pdf: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)


class ParserTest(unittest.TestCase):
    def test_datum(self):
        self.assertEqual(parse_date("07.04.2026"), date(2026, 4, 7))
        self.assertEqual(parse_date("7.4.26"), date(2026, 4, 7))
        self.assertEqual(parse_date("070426"), date(2026, 4, 7))
        self.assertEqual(parse_date("2026-04-07"), date(2026, 4, 7))
        self.assertEqual(parse_date("7.4.", default_year=2025), date(2025, 4, 7))
        for falsch in ("", "31.02.2026", "abc", "7/4/2026"):
            with self.assertRaises(ValueError):
                parse_date(falsch)

    def test_uhrzeit(self):
        for text, erwartet in (("11:59", (11, 59)), ("1159", (11, 59)), ("959", (9, 59)),
                               ("11.59", (11, 59)), ("11", (11, 0)), ("15:00 Uhr", (15, 0))):
            t = parse_time(text)
            self.assertEqual((t.hour, t.minute), erwartet, text)
        for falsch in ("24:00", "12:60", "x", ""):
            with self.assertRaises(ValueError):
                parse_time(falsch)


class PlatzhalterTest(unittest.TestCase):
    def ctx(self, c, start, end):
        return build_context(c, "2026-117", start, end, start, end, date(2026, 4, 9))

    def test_standardtext(self):
        s, e = datetime(2026, 4, 7, 11, 59), datetime(2026, 4, 7, 15, 0)
        text = render(DEFAULT_TEMPLATE["text"], self.ctx(MAX, s, e), 0)
        self.assertIn("dass Herr Max Mustermann im Rahmen seiner ehrenamtlichen Tätigkeit am "
                      "07.04.2026 als Einsatzkraft von 11:59 Uhr bis 15:00 Uhr im Einsatz war.", text)

    def test_weiblich_und_folgetag(self):
        s, e = datetime(2026, 4, 7, 23, 10), datetime(2026, 4, 8, 2, 30)
        ctx = self.ctx(ANNA, s, e)
        text = render(DEFAULT_TEMPLATE["text"], ctx, gender_index("Frau"))
        self.assertIn("dass Frau Anna Müller im Rahmen ihrer", text)
        self.assertIn("bis 08.04.2026, 02:30 Uhr", text)
        self.assertEqual(ctx["Dauer"], "3:20 Std.")
        self.assertIn("vom 07.04.2026, 23:10 Uhr bis zum 08.04.2026, 02:30 Uhr", ctx["Zeitraum"])
        self.assertEqual(render("{Herrn/Frau}", ctx, 1), "Frau")

    def test_ohne_anrede_und_unbekannt(self):
        unbekannt = set()
        out = render("dass {Herr/Frau} {Name} {Foo}", {"Name": "Kim Lee"}, 2, unbekannt)
        self.assertEqual(out, "dass Kim Lee {Foo}")
        self.assertEqual(unbekannt, {"{Foo}"})
        self.assertEqual(unknown_placeholders(DEFAULT_TEMPLATE), [])

    def test_dateiname(self):
        s = datetime(2026, 4, 7, 11, 59)
        name = safe_filename(render(DEFAULT_TEMPLATE["dateiname"], self.ctx(MAX, s, s), 0))
        self.assertEqual(name, "2026-04-07_1159_Einsatzbescheinigung_Mustermann_Max")
        self.assertEqual(safe_filename('a/b:c*d "von der" Heyde'), "a-b-c-d_-von_der-_Heyde")


class PdfTest(unittest.TestCase):
    def test_erzeugen(self):
        tmp = Path(tempfile.mkdtemp())
        store = Store(tmp / "daten")
        tpl = copy.deepcopy(DEFAULT_TEMPLATE)
        s, e = datetime(2026, 4, 7, 11, 59), datetime(2026, 4, 7, 15, 0)
        einsatz = Einsatz("2026-117", s, e, date(2026, 4, 9))
        doppel = dict(MAX, id="k-max-2")
        teil = [Teilnahme(MAX, s, e), Teilnahme(ANNA, s, datetime(2026, 4, 7, 14, 0)),
                Teilnahme(doppel, s, e)]
        for system in (False, True):
            ordner = einsatz_ordner(tmp / "out", einsatz)
            ergebnisse, ordner = erzeuge(einsatz, teil, tpl, store.assets, ordner,
                                         use_system_fonts=system)
            self.assertEqual(ordner.name, "2026-04-07_1159_Einsatz_2026-117")
            namen = [r.pdf.name for r in ergebnisse]
            self.assertEqual(namen[0], "2026-04-07_1159_Einsatzbescheinigung_Mustermann_Max.pdf")
            self.assertEqual(namen[2], "2026-04-07_1159_Einsatzbescheinigung_Mustermann_Max_2.pdf")
            for r in ergebnisse:
                self.assertTrue(r.pdf.read_bytes().startswith(b"%PDF"))
                self.assertEqual(seiten(r.pdf), 1)
            self.assertEqual(ergebnisse[0].betreff, "Einsatzbescheinigung – Einsatz 2026-117 am 07.04.2026")
            rec = eintragen(None, einsatz, ergebnisse, ordner)
            sammel, fehlen = erstelle_sammel(rec)
            self.assertEqual(fehlen, [])
            self.assertEqual(sammel.name, "2026-04-07_1159_Einsatz_2026-117_Alle_Bescheinigungen.pdf")
            self.assertEqual(seiten(sammel), 3)

    def test_mitgelieferte_schriften(self):
        for fam in ("Arial Narrow", "Arial"):
            for path in resolve_fonts(fam, use_system=False):
                self.assertTrue(Path(path).is_file(), path)


class ImportTest(unittest.TestCase):
    def test_csv_semikolon(self):
        tmp = Path(tempfile.mkdtemp()) / "liste.csv"
        tmp.write_text("Anrede;DG;Name;Vorname;Straße;PLZ;Ort;E-Mail\n"
                       "Herr;OFM;Mustermann;Max;Musterweg 1;1067;Musterstadt;max@example.org\n"
                       "w;HFF;Müller;Anna;;12345;Musterstadt;\n;;;;;;;\n", encoding="cp1252")
        headers, rows = lese_tabelle(tmp)
        mapping = auto_zuordnung(headers)
        self.assertEqual(headers[mapping["nachname"]], "Name")
        self.assertEqual(headers[mapping["dienstgrad"]], "DG")
        kontakte = wende_an(headers, rows, mapping)
        self.assertEqual(len(kontakte), 2)
        self.assertEqual(kontakte[0]["plz"], "01067")
        self.assertEqual(kontakte[1]["anrede"], "Frau")
        self.assertEqual(kontakte[1]["nachname"], "Müller")

    def test_excel_name_komplett(self):
        from openpyxl import Workbook

        tmp = Path(tempfile.mkdtemp()) / "liste.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["Name", "PLZ Ort", "Mail"])
        ws.append(["Mustermann, Max", "12345 Musterstadt", "max@example.org"])
        ws.append(["Anna Maria Müller", "12345 Musterstadt", None])
        wb.save(tmp)
        headers, rows = lese_tabelle(tmp)
        kontakte = wende_an(headers, rows, auto_zuordnung(headers))
        self.assertEqual((kontakte[0]["vorname"], kontakte[0]["nachname"]), ("Max", "Mustermann"))
        self.assertEqual((kontakte[1]["vorname"], kontakte[1]["nachname"]), ("Anna Maria", "Müller"))
        self.assertEqual((kontakte[0]["plz"], kontakte[0]["ort"]), ("12345", "Musterstadt"))

    def test_dubletten(self):
        store = Store(Path(tempfile.mkdtemp()))
        self.assertEqual(store.add_contacts([MAX, ANNA]), (2, 0))
        self.assertEqual(store.add_contacts([MAX]), (0, 1))
        self.assertEqual([c["nachname"] for c in store.contacts], ["Müller", "Mustermann"])


class VorlageTest(unittest.TestCase):
    def test_export_import(self):
        tmp = Path(tempfile.mkdtemp())
        a = Store(tmp / "a")
        img = tmp / "logo.png"
        from PIL import Image

        Image.new("RGB", (20, 10), "red").save(img)
        a.template["logo_links"]["datei"] = a.import_image("logo_links", img)
        a.template["titel"] = "Test-Titel"
        a.save_template()
        a.export_template(tmp / "v.einsatzvorlage")
        b = Store(tmp / "b")
        b.import_template(tmp / "v.einsatzvorlage")
        self.assertEqual(b.template["titel"], "Test-Titel")
        self.assertIsNotNone(b.image_path(b.template["logo_links"]["datei"]))


class VerlaufTest(unittest.TestCase):
    """Einsatz speichern und später einen vergessenen Kameraden ergänzen."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / "daten")
        self.s, self.e = datetime(2026, 4, 7, 11, 59), datetime(2026, 4, 7, 15, 0)

    def lauf(self, teilnahmen, nummer="2026-117", ausgestellt=date(2026, 4, 9)):
        einsatz = Einsatz(nummer, self.s, self.e, ausgestellt)
        rec = finde(self.store.einsaetze, nummer, self.s)
        ordner = einsatz_ordner(self.tmp / "out", einsatz)
        neu = {kontakt_schluessel(t.contact) for t in teilnahmen}
        ergebnisse, ordner = erzeuge(einsatz, teilnahmen, DEFAULT_TEMPLATE, self.store.assets,
                                     ordner, belegte_namen(rec, neu), use_system_fonts=False)
        rec = eintragen(rec, einsatz, ergebnisse, ordner)
        self.store.upsert_einsatz(rec)
        return rec, ergebnisse

    def test_kamerad_nachtragen(self):
        rec, erg = self.lauf([Teilnahme(MAX, self.s, self.e), Teilnahme(ANNA, self.s, self.e)])
        max_pdf = erg[0].pdf.read_bytes()
        sammel, _ = erstelle_sammel(rec)
        self.assertEqual(seiten(sammel), 2)

        # Neustart der App: Einsatz wird wiedererkannt, Erika wird ergänzt
        self.store = Store(self.tmp / "daten")
        self.assertIsNotNone(finde(self.store.einsaetze, "2026-117", self.s))
        self.assertIsNone(finde(self.store.einsaetze, "2026-117", datetime(2026, 4, 7, 12, 0)))
        self.assertIsNone(finde(self.store.einsaetze, "2026-118", self.s))
        rec2, erg2 = self.lauf([Teilnahme(ERIKA, self.s, datetime(2026, 4, 7, 14, 0))],
                               ausgestellt=date(2026, 4, 20))
        self.assertEqual(rec2["id"], rec["id"])
        self.assertEqual(len(self.store.einsaetze), 1)
        self.assertEqual([t["kontakt"]["nachname"] for t in rec2["teilnehmer"]],
                         ["Müller", "Musterfrau", "Mustermann"])
        self.assertEqual(erg2[0].pdf.parent, erg[0].pdf.parent)
        self.assertEqual(erg[0].pdf.read_bytes(), max_pdf)  # vorhandene PDFs bleiben unverändert
        sammel, fehlen = erstelle_sammel(rec2)
        self.assertEqual((seiten(sammel), fehlen), (3, []))
        self.assertEqual(teilnehmer(rec2)["k-erika"]["ausstellungsdatum"], "2026-04-20")

        # Bereits bescheinigte Kameradin neu erstellen: ersetzt, nicht verdoppelt
        rec3, _ = self.lauf([Teilnahme(ANNA, self.s, datetime(2026, 4, 7, 13, 0))])
        self.assertEqual(len(rec3["teilnehmer"]), 3)
        self.assertEqual(teilnehmer(rec3)["k-anna"]["ende"], "2026-04-07T13:00")

    def test_namensgleichheit_ueberschreibt_nicht(self):
        rec, erg = self.lauf([Teilnahme(MAX, self.s, self.e)])
        zwilling = dict(MAX, id="k-anderer-max")
        rec2, erg2 = self.lauf([Teilnahme(zwilling, self.s, self.e)])
        self.assertNotEqual(erg2[0].pdf, erg[0].pdf)
        self.assertTrue(erg2[0].pdf.name.endswith("_Mustermann_Max_2.pdf"))
        self.assertEqual(len(rec2["teilnehmer"]), 2)

    def test_fehlende_datei(self):
        rec, erg = self.lauf([Teilnahme(MAX, self.s, self.e), Teilnahme(ANNA, self.s, self.e)])
        erg[1].pdf.unlink()
        sammel, fehlen = erstelle_sammel(rec)
        self.assertEqual((seiten(sammel), fehlen), (1, ["Müller, Anna"]))

    def test_entfernen(self):
        rec, _ = self.lauf([Teilnahme(MAX, self.s, self.e)])
        self.store.delete_einsatz(rec["id"])
        self.assertEqual(Store(self.tmp / "daten").einsaetze, [])


class BeispielvorlageTest(unittest.TestCase):
    def test_beispielvorlage(self):
        datei = resource_dir() / BEISPIELVORLAGE
        self.assertTrue(datei.is_file())
        store = Store(Path(tempfile.mkdtemp()))
        store.ersteinrichtung()
        for slot in BILD_FELDER:
            self.assertIsNotNone(store.image_path(store.template[slot]["datei"]), slot)
        # Texte der Beispieldatei = eingebaute Standardtexte (tools/beispielvorlage_erzeugen.py)
        for key, wert in DEFAULT_TEMPLATE.items():
            if isinstance(wert, str):
                self.assertEqual(store.template[key], wert, key)
        self.assertIn("Sabine Musterfrau", store.template["unterzeichner"])
        r = Renderer(store.template, store.assets, use_system_fonts=False)
        ctx, gender = demo_context()
        r.add_page(ctx, gender)
        ziel = Path(tempfile.mkdtemp()) / "b.pdf"
        r.save(ziel, title="Beispiel")
        self.assertEqual(seiten(ziel), 1)

    def test_ersteinrichtung_ueberschreibt_nichts(self):
        store = Store(Path(tempfile.mkdtemp()))
        store.template["titel"] = "Eigener Titel"
        store.save_template()
        store.ersteinrichtung()
        self.assertEqual(store.template["titel"], "Eigener Titel")


class EmlTest(unittest.TestCase):
    def test_eml(self):
        tmp = Path(tempfile.mkdtemp())
        pdf = tmp / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        path = schreibe_eml(Entwurf("max@example.org", "Betreff – ä", "Hallo\nZeile 2", [pdf],
                                    ["lz@example.org"]), tmp)
        msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        self.assertEqual(msg["X-Unsent"], "1")
        self.assertEqual(msg["Bcc"], "lz@example.org")
        self.assertEqual(msg["Subject"], "Betreff – ä")
        self.assertEqual([p.get_filename() for p in msg.iter_attachments()], ["x.pdf"])


if __name__ == "__main__":
    unittest.main()
