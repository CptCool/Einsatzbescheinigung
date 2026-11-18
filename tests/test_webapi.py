"""Tests der Schnittstelle der Browser-Version (laufen in normalem Python, ohne Browser).

Start: python -m unittest discover -s tests -t .
"""

import email
import email.policy
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

from pypdf import PdfReader

from einsatzapp import webapi


def seiten(pfad) -> int:
    return len(PdfReader(str(pfad)).pages)


class WebApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="eb_webapi_"))
        patcher = mock.patch.dict(os.environ, {"EINSATZBESCHEINIGUNG_DATEN": str(self.tmp / "daten")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.info = webapi.start()

    def kontakt(self, vorname, nachname, email="", anrede="Herr"):
        return webapi.kontakt_speichern({"anrede": anrede, "vorname": vorname, "nachname": nachname,
                                         "email": email, "dienstgrad": "OFM", "strasse": "Hauptstraße 1",
                                         "plz": "12345", "ort": "Musterstadt"})

    def einsatz(self, nummer="2026-117"):
        return {"nummer": nummer, "sd": "07.04.2026", "st": "11:59", "ed": "07.04.2026", "et": "15:00",
                "ausst": "09.04.2026"}

    def zeilen(self, *kontakte):
        return [{"id": k["id"], "sd": "07.04.2026", "st": "11:59", "ed": "07.04.2026", "et": "15:00"}
                for k in kontakte]

    # ------------------------------------------------------------------ Grundlagen
    def test_start_richtet_beispielvorlage_ein(self):
        self.assertEqual(self.info["kontakte"], [])
        self.assertTrue((self.tmp / "daten" / "vorlage.json").is_file())
        v = webapi.vorlage()
        self.assertIn("Musterfrau", v["formular"]["unterzeichner"])
        self.assertTrue(v["bilder"]["unterschrift"].startswith("data:image/png;base64,"))
        self.assertEqual(v["formular"]["logo_links"]["x"], "25,3")

    def test_aufruf_json(self):
        ok = json.loads(webapi.aufruf("kontakt_speichern", json.dumps({"werte": {"vorname": "Max"}})))
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["wert"]["vorname"], "Max")
        hinweis = json.loads(webapi.aufruf("kontakt_speichern", json.dumps({"werte": {"email": "x"}})))
        self.assertEqual(hinweis, {"ok": False, "meldung": "Bitte mindestens Vor- oder Nachnamen eingeben."})
        fehler = json.loads(webapi.aufruf("kontakt_loeschen", "{}"))
        self.assertFalse(fehler["ok"])
        self.assertIn("Traceback", fehler["fehler"])
        self.assertIn("Unbekannte Funktion", json.loads(webapi.aufruf("os.system", "{}"))["fehler"])

    def test_kontakt_pruefung_und_anrede(self):
        with self.assertRaises(webapi.Hinweis):
            self.kontakt("Max", "Mustermann", email="kein-mail")
        k = self.kontakt("Max", "Mustermann", anrede="keine Angabe")
        self.assertEqual(k["anrede"], "")
        k2 = webapi.kontakt_speichern({**k, "ort": "Neustadt"})
        self.assertEqual(k2["id"], k["id"])
        self.assertEqual([c["ort"] for c in webapi.kontakte()], ["Neustadt"])

    def test_import_aus_csv(self):
        csv = self.tmp / "liste.csv"
        csv.write_text("Anrede;Vorname;Nachname;E-Mail\nHerr;Max;Mustermann;max@example.org\n"
                       "Frau;Erika;Musterfrau;\n", encoding="utf-8")
        t = webapi.tabelle_lesen(str(csv))
        self.assertEqual(t["zuordnung"]["vorname"], 1)
        v = webapi.import_vorschau(t["kopf"], t["zeilen"], t["zuordnung"])
        self.assertEqual((v["anzahl"], v["ohne_mail"]), (2, 1))
        self.assertEqual(webapi.kontakte_importieren(t["kopf"], t["zeilen"], t["zuordnung"]),
                         {"neu": 2, "uebersprungen": 0})
        self.assertEqual(webapi.kontakte_importieren(t["kopf"], t["zeilen"], t["zuordnung"]),
                         {"neu": 0, "uebersprungen": 2})
        with self.assertRaises(webapi.Hinweis):
            webapi.kontakte_importieren(t["kopf"], t["zeilen"], {})
        export = webapi.kontakte_exportieren()
        self.assertIn("Musterfrau", Path(export["pfad"]).read_text(encoding="utf-8-sig"))

    def test_vorlage_speichern_und_pruefen(self):
        v = webapi.vorlage()
        f = v["formular"]
        f["titel"] = "Bescheinigung {Gibtsnicht}"
        f["logo_links"]["b"] = "40,5"
        self.assertEqual(webapi.vorlage_pruefen(f, "Arial")["unbekannt"], ["{Gibtsnicht}"])
        self.assertEqual(webapi.vorlage_speichern(f, "Arial")["unbekannt"], ["{Gibtsnicht}"])
        neu = webapi.vorlage()
        self.assertEqual(neu["formular"]["logo_links"]["b"], "40,5")
        self.assertEqual(neu["schrift"], "Arial")
        f["logo_links"]["b"] = "breit"
        with self.assertRaises(webapi.Hinweis):
            webapi.vorlage_speichern(f, "Arial")
        self.assertEqual(seiten(webapi.vorschau(neu["formular"], "Arial")["pfad"]), 1)
        self.assertEqual(webapi.dateiname_beispiel("{Nachname}_{Vorname}"), "Mustermann_Max.pdf")
        # Export und wieder Import
        export = webapi.vorlage_exportieren()
        self.assertEqual(webapi.vorlage_importieren(export["pfad"])["formular"]["logo_links"]["b"], "40,5")
        kaputt = self.tmp / "x.einsatzvorlage"
        kaputt.write_text('{"format": "anders"}', encoding="utf-8")
        with self.assertRaises(webapi.Hinweis):
            webapi.vorlage_importieren(str(kaputt))

    def test_bild_uebernehmen(self):
        kein_bild = self.tmp / "logo.png"
        kein_bild.write_bytes(b"kein Bild")
        with self.assertRaises(webapi.Hinweis):
            webapi.bild_uebernehmen("logo_links", str(kein_bild))
        from PIL import Image

        Image.new("RGB", (40, 20), "red").save(kein_bild)
        r = webapi.bild_uebernehmen("logo_links", str(kein_bild))
        self.assertTrue(r["datei"].startswith("logo_links_"))
        self.assertTrue(r["bild"].startswith("data:image/png;base64,"))

    # ------------------------------------------------------------------ Einsatz
    def test_einsatz_pruefen_folgetag(self):
        p = webapi.einsatz_pruefen("1", "07.04.2026", "22:00", "07.04.2026", "01:30")
        self.assertEqual(p["dauer"], "Dauer: 3:30 Std. · Ende am Folgetag")
        self.assertIsNone(p["treffer"])
        self.assertEqual(webapi.einsatz_pruefen("1", "07.04.2026", "22:00", "06.04.2026", "23:00")["fehler"],
                         "Ende liegt vor dem Beginn")
        self.assertEqual(webapi.einsatz_pruefen("1", "07.04.2026", "", "", "")["dauer"], "")

    def test_weiter_prueft_und_fragt(self):
        max_ = self.kontakt("Max", "Mustermann", "max@example.org")
        with self.assertRaises(webapi.Hinweis):
            webapi.weiter(**self.einsatz(), auswahl=[])
        w = webapi.weiter(**{**self.einsatz(nummer=""), "ed": "09.04.2026"}, auswahl=[max_["id"]])
        self.assertEqual(len(w["fragen"]), 2)  # über 24 Stunden + keine Nummer
        w = webapi.weiter(**self.einsatz(), auswahl=[max_["id"]])
        self.assertEqual(w["fragen"], [])
        self.assertEqual(w["standard"], {"sd": "07.04.2026", "st": "11:59", "ed": "07.04.2026", "et": "15:00"})
        self.assertIn("Einsatz 2026-117", w["kopf"])
        z = webapi.zeilen_pruefen(w["standard"], {max_["id"]: {**w["standard"], "et": "16:00"}})
        self.assertEqual(z[max_["id"]], {"text": "4:01 Std.  · angepasst", "art": "info"})

    def test_erstellen_nachtragen_und_verwalten(self):
        max_ = self.kontakt("Max", "Mustermann", "max@example.org")
        erika = self.kontakt("Erika", "Musterfrau", "", anrede="Frau")
        anna = self.kontakt("Anna", "Beispiel", "anna@example.org", anrede="Frau")
        webapi.einstellungen_speichern("lz1@example.org", True, True)

        self.assertEqual(len(webapi.erstellen_pruefen(self.zeilen(max_, erika), mails=True)["fragen"]), 1)
        r = webapi.erstellen(**self.einsatz(), zeilen=self.zeilen(max_, erika), mails=True, sammel=True)
        self.assertFalse(r["ergaenzt"])
        self.assertEqual(r["gesamt"], 2)
        self.assertEqual(seiten(r["sammel"]), 2)
        zeile_max = next(z for z in r["zeilen"] if z["name"] == "Mustermann, Max")
        self.assertTrue(Path(zeile_max["pdf"]).is_file())
        self.assertEqual(zeile_max["email"], "max@example.org")
        self.assertEqual(zeile_max["betreff"], "Einsatzbescheinigung – Einsatz 2026-117 am 07.04.2026")
        self.assertTrue(zeile_max["text"].startswith("Hallo Max,"))
        msg = email.message_from_bytes(Path(zeile_max["eml"]).read_bytes(), policy=email.policy.default)
        self.assertEqual((msg["To"], msg["Bcc"], msg["X-Unsent"]), ("max@example.org", "lz1@example.org", "1"))
        self.assertEqual([a.get_filename() for a in msg.iter_attachments()], [zeile_max["pdf_name"]])
        url = urlsplit(zeile_max["mailto"])
        self.assertEqual(unquote(url.path), "max@example.org")
        q = parse_qs(url.query)
        self.assertEqual(q["bcc"], ["lz1@example.org"])
        self.assertIn("\r\n", q["body"][0])
        zeile_erika = next(z for z in r["zeilen"] if z["name"] == "Musterfrau, Erika")
        self.assertFalse(zeile_erika["ok"])
        self.assertIsNone(zeile_erika["eml"])
        with zipfile.ZipFile(r["zip"]) as z:
            self.assertEqual(len([n for n in z.namelist() if n.endswith(".pdf")]), 3)  # 2 + Sammel-PDF
            self.assertEqual(len([n for n in z.namelist() if n.endswith(".eml")]), 1)
        self.assertTrue(r["zeilen"][0]["pdf"].startswith(str(self.tmp / "daten" / "ablage")))

        # gespeichert und erkannt
        p = webapi.einsatz_pruefen("2026-117", "07.04.2026", "11:59", "07.04.2026", "15:00")
        self.assertEqual(p["treffer"]["anzahl"], 2)
        self.assertIn(max_["id"], p["treffer"]["status"])
        w = webapi.weiter(**self.einsatz(), auswahl=[max_["id"], anna["id"]])
        self.assertTrue(w["ergaenzung"])
        gespeichert = {z["id"]: z["gespeichert"] for z in w["zeilen"]}
        self.assertIsNotNone(gespeichert[max_["id"]])
        self.assertIsNone(gespeichert[anna["id"]])

        # Anna nachtragen: alte PDFs bleiben, Sammel-PDF hat jetzt 3 Seiten
        alt = Path(zeile_max["pdf"]).read_bytes()
        r2 = webapi.erstellen(**self.einsatz(), zeilen=self.zeilen(anna), mails=True, sammel=True)
        self.assertTrue(r2["ergaenzt"])
        self.assertEqual(r2["gesamt"], 3)
        self.assertEqual(seiten(r2["sammel"]), 3)
        self.assertEqual(Path(zeile_max["pdf"]).read_bytes(), alt)
        self.assertTrue(r2["zip_name"].endswith("_Ergaenzung.zip"))

        liste = webapi.einsaetze()
        self.assertEqual([(e["nummer"], e["anzahl"]) for e in liste], [("2026-117", 3)])
        self.assertEqual(webapi.einsaetze("gibtsnicht"), [])
        eid = liste[0]["id"]
        d = webapi.einsatz_details(eid)
        self.assertTrue(d["sammel"])
        self.assertTrue(all(t["vorhanden"] for t in d["teilnehmer"]))
        self.assertEqual(webapi.einsatz_laden(eid)["st"], "11:59")
        with zipfile.ZipFile(webapi.einsatz_paket(eid)["pfad"]) as z:
            self.assertEqual(len(z.namelist()), 4)
        self.assertEqual(seiten(webapi.einsatz_sammel(eid)["pfad"]), 3)
        ordner = Path(r["zeilen"][0]["pdf"]).parent
        webapi.einsatz_entfernen(eid)
        self.assertEqual(webapi.einsaetze(), [])
        self.assertFalse(ordner.exists())

    # ------------------------------------------------------------------ Datensicherung
    def test_datensicherung(self):
        max_ = self.kontakt("Max", "Mustermann", "max@example.org")
        webapi.erstellen(**self.einsatz(), zeilen=self.zeilen(max_), mails=False, sammel=True)
        self.assertEqual(webapi.speicherbedarf()["einsaetze"], 1)
        sicherung = webapi.datensicherung()
        with zipfile.ZipFile(sicherung["pfad"]) as z:
            namen = z.namelist()
        self.assertIn("datensicherung.json", namen)
        self.assertIn("kontakte.json", namen)
        self.assertTrue(any(n.startswith("ablage/") and n.endswith(".pdf") for n in namen))

        webapi.kontakt_loeschen(max_["id"])
        self.kontakt("Anna", "Beispiel")
        geladen = webapi.datensicherung_laden(sicherung["pfad"])
        self.assertEqual([k["vorname"] for k in geladen["kontakte"]], ["Max"])
        self.assertEqual(len(webapi.einsaetze()), 1)
        self.assertTrue(all(t["vorhanden"] for t in webapi.einsatz_details(webapi.einsaetze()[0]["id"])["teilnehmer"]))

    def test_datensicherung_abgelehnt(self):
        fremd = self.tmp / "fremd.zip"
        with zipfile.ZipFile(fremd, "w") as z:
            z.writestr("kontakte.json", "[]")
        with self.assertRaises(webapi.Hinweis):
            webapi.datensicherung_laden(str(fremd))
        boese = self.tmp / "boese.zip"
        with zipfile.ZipFile(boese, "w") as z:
            z.writestr("datensicherung.json", json.dumps({"format": webapi.SICHERUNG_FORMAT}))
            z.writestr("../ausserhalb.txt", "x")
        with self.assertRaises(webapi.Hinweis):
            webapi.datensicherung_laden(str(boese))
        self.assertFalse((self.tmp / "ausserhalb.txt").exists())
        self.assertTrue((self.tmp / "daten" / "vorlage.json").is_file())  # nichts gelöscht

    def test_temp_ordner_werden_aufgeraeumt(self):
        ordner = [webapi._temp("x") for _ in range(webapi.TEMP_BEHALTEN + 5)]
        self.assertFalse(ordner[0].exists())
        self.assertTrue(ordner[-1].exists())

    def test_lizenzen(self):
        self.assertIn("MIT License", webapi.lizenzen())


if __name__ == "__main__":
    unittest.main()
