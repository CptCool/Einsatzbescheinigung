"""Bereich „Vorlage“: Briefkopf, Texte, Unterschrift, E-Mail-Text und Dateiname bearbeiten."""

import copy
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .generator import unknown_placeholders, vorschau
from .paths import open_path
from .pdfgen import SCHRIFTEN
from .placeholders import PLATZHALTER_HILFE, demo_context, render, safe_filename
from .storage import BILD_FELDER, DEFAULT_TEMPLATE
from .widgets import ScrollFrame, text_get, text_set, text_widget

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


class VorlageTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.store = app.store
        self.felder: dict = {}
        self.bilder: dict = {}
        self._fokus = None
        self._snapshot = None
        self._thumbs = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Vorlage", style="Titel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.sf = ScrollFrame(self)
        self.sf.grid(row=1, column=0, sticky="nsew")
        self._baue_formular(self.sf.inner)
        self._baue_seitenleiste()
        self.lade()

    # ------------------------------------------------------------------ Aufbau
    def _baue_formular(self, parent):
        parent.columnconfigure(0, weight=1)
        for r, (titel, felder) in enumerate(ABSCHNITTE):
            box = ttk.LabelFrame(parent, text=titel, padding=(12, 8))
            box.grid(row=r, column=0, sticky="ew", padx=(0, 10), pady=(0, 12))
            box.columnconfigure(1, weight=1)
            zeile = 0
            for key, label, art, hoehe, hinweis in felder:
                if art == "bild":
                    self._bild_zeile(box, zeile, key)
                    zeile += 1
                    continue
                ttk.Label(box, text=label).grid(row=zeile, column=0, sticky="nw", padx=(0, 10), pady=4)
                if art == "entry":
                    var = tk.StringVar()
                    w = ttk.Entry(box, textvariable=var)
                    w.grid(row=zeile, column=1, sticky="ew", pady=4)
                    self.felder[key] = ("entry", var, w)
                elif art == "schrift":
                    var = tk.StringVar()
                    w = ttk.Combobox(box, textvariable=var, values=SCHRIFTEN, state="readonly", width=18)
                    w.grid(row=zeile, column=1, sticky="w", pady=4)
                    self.felder[key] = ("entry", var, w)
                else:
                    w = text_widget(box, height=hoehe)
                    w.grid(row=zeile, column=1, sticky="ew", pady=4)
                    self.felder[key] = ("text", None, w)
                if art != "schrift":
                    w.bind("<FocusIn>", lambda e: setattr(self, "_fokus", e.widget), add="+")
                zeile += 1
                if hinweis:
                    ttk.Label(box, text=hinweis, style="Hinweis.TLabel", wraplength=560).grid(
                        row=zeile, column=1, sticky="w", pady=(0, 4))
                    zeile += 1
                if key == "dateiname":
                    self.lbl_beispiel = ttk.Label(box, text="", style="Hinweis.TLabel")
                    self.lbl_beispiel.grid(row=zeile, column=1, sticky="w")
                    self.felder[key][1].trace_add("write", lambda *_: self._zeige_beispiel())
                    zeile += 1

    def _bild_zeile(self, box, zeile, slot):
        rahmen = ttk.Frame(box)
        rahmen.grid(row=zeile, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        ttk.Label(rahmen, text=BILD_TITEL[slot], style="Fett.TLabel").grid(row=0, column=0, sticky="w")
        vorschau_lbl = ttk.Label(rahmen, text="(kein Bild)", style="Hinweis.TLabel", width=20, anchor="center")
        vorschau_lbl.grid(row=1, column=0, rowspan=2, sticky="w", padx=(0, 14), pady=(4, 0))
        knoepfe = ttk.Frame(rahmen)
        knoepfe.grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Button(knoepfe, text="Bild wählen …", command=lambda: self._bild_waehlen(slot)).pack(side="left")
        ttk.Button(knoepfe, text="Entfernen", command=lambda: self._bild_entfernen(slot)).pack(side="left", padx=6)
        masse = ttk.Frame(rahmen)
        masse.grid(row=2, column=1, sticky="w", pady=(6, 0))
        vars_ = {"datei": tk.StringVar()}
        for i, (key, label) in enumerate(BILD_MASSE[slot]):
            ttk.Label(masse, text=label).grid(row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 12, 4))
            vars_[key] = tk.StringVar()
            ttk.Entry(masse, textvariable=vars_[key], width=6).grid(row=0, column=i * 2 + 1, sticky="w")
        ttk.Label(masse, text="mm", style="Hinweis.TLabel").grid(row=0, column=len(BILD_MASSE[slot]) * 2,
                                                                 padx=(6, 0))
        self.bilder[slot] = {"vars": vars_, "vorschau": vorschau_lbl}

    def _baue_seitenleiste(self):
        seite = ttk.Frame(self)
        seite.grid(row=1, column=1, sticky="ns", padx=(10, 0))
        seite.rowconfigure(1, weight=1)
        aktionen = ttk.LabelFrame(seite, text="Aktionen", padding=10)
        aktionen.grid(row=0, column=0, sticky="ew")
        ttk.Button(aktionen, text="Speichern", style="Primar.TButton", command=self.speichern).pack(fill="x")
        ttk.Button(aktionen, text="Vorschau-PDF öffnen", command=self._vorschau).pack(fill="x", pady=(8, 0))
        ttk.Button(aktionen, text="Änderungen verwerfen", command=self._verwerfen).pack(fill="x", pady=(4, 0))
        self.lbl_status = ttk.Label(aktionen, text="", style="Hinweis.TLabel", wraplength=230)
        self.lbl_status.pack(fill="x", pady=(8, 0))
        ttk.Separator(aktionen).pack(fill="x", pady=10)
        ttk.Button(aktionen, text="Vorlage exportieren …", command=self._export).pack(fill="x")
        ttk.Button(aktionen, text="Vorlage importieren …", command=self._import).pack(fill="x", pady=(4, 0))
        ttk.Button(aktionen, text="Beispieltexte (Musterstadt) einsetzen",
                   command=self._standard).pack(fill="x", pady=(4, 0))

        ph = ttk.LabelFrame(seite, text="Platzhalter", padding=10)
        ph.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        ph.rowconfigure(1, weight=1)
        ttk.Label(ph, text="Doppelklick fügt den Platzhalter an der Cursorposition ein.",
                  style="Hinweis.TLabel", wraplength=230).grid(row=0, column=0, columnspan=2, sticky="w",
                                                                pady=(0, 6))
        tree = ttk.Treeview(ph, columns=("ph", "info"), show="headings", height=14, selectmode="browse")
        tree.heading("ph", text="Platzhalter", anchor="w")
        tree.heading("info", text="Bedeutung", anchor="w")
        tree.column("ph", width=150, anchor="w")
        tree.column("info", width=230, anchor="w")
        for platzhalter, info in PLATZHALTER_HILFE:
            tree.insert("", "end", values=(platzhalter, info))
        vsb = ttk.Scrollbar(ph, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        tree.bind("<Double-1>", lambda _e: self._einfuegen(tree))
        ttk.Button(ph, text="Einfügen", command=lambda: self._einfuegen(tree)).grid(
            row=2, column=0, columnspan=2, sticky="e", pady=(6, 0))

    # ------------------------------------------------------------------ Werte
    def _werte_roh(self) -> dict:
        out = {}
        for key, (art, var, w) in self.felder.items():
            out[key] = var.get() if art == "entry" else text_get(w)
        for slot, info in self.bilder.items():
            out[slot] = {k: v.get() for k, v in info["vars"].items()}
        return out

    def _werte(self) -> dict:
        """Formularwerte als Vorlage; wirft ValueError bei ungültigen Maßen."""
        roh = self._werte_roh()
        tpl = copy.deepcopy(self.store.template)
        for key in self.felder:
            tpl[key] = roh[key]
        for slot in BILD_FELDER:
            spec = {"datei": roh[slot]["datei"]}
            for key, label in BILD_MASSE[slot]:
                text = roh[slot][key].strip().replace(",", ".") or "0"
                try:
                    spec[key] = round(float(text), 2)
                except ValueError:
                    raise ValueError(f"{BILD_TITEL[slot]}: „{roh[slot][key]}“ ist keine Zahl ({label}).") from None
            tpl[slot] = spec
        return tpl

    def lade(self):
        tpl = self.store.template
        for key, (art, var, w) in self.felder.items():
            if art == "entry":
                var.set(tpl.get(key, ""))
            else:
                text_set(w, tpl.get(key, ""))
        for slot, info in self.bilder.items():
            spec = tpl.get(slot) or {}
            for key, var in info["vars"].items():
                val = spec.get(key, "")
                var.set(f"{val:g}".replace(".", ",") if isinstance(val, (int, float)) else str(val))
            self._zeige_bild(slot)
        self._snapshot = self._werte_roh()
        self._zeige_beispiel()
        self.lbl_status.configure(text="")

    def ist_geaendert(self) -> bool:
        return self._snapshot is not None and self._werte_roh() != self._snapshot

    def verlassen(self) -> bool:
        if not self.ist_geaendert():
            return True
        antwort = messagebox.askyesnocancel("Ungespeicherte Änderungen",
                                            "Die Vorlage wurde geändert. Änderungen speichern?", parent=self)
        if antwort is None:
            return False
        if antwort:
            return self.speichern()
        self.lade()
        return True

    def speichern(self) -> bool:
        try:
            tpl = self._werte()
        except ValueError as err:
            messagebox.showerror("Bitte prüfen", str(err), parent=self)
            return False
        unbekannt = unknown_placeholders(tpl)
        self.store.template = tpl
        self.store.save_template()
        self._snapshot = self._werte_roh()
        if unbekannt:
            self.lbl_status.configure(text="Gespeichert. Achtung, unbekannte Platzhalter: "
                                      + ", ".join(unbekannt), style="Fehler.TLabel")
        else:
            self.lbl_status.configure(text="Vorlage gespeichert.", style="Ok.TLabel")
        return True

    def _verwerfen(self):
        self.lade()
        self.lbl_status.configure(text="Änderungen verworfen.", style="Hinweis.TLabel")

    def _zeige_beispiel(self):
        if not hasattr(self, "lbl_beispiel"):
            return
        ctx, gender = demo_context()
        muster = self.felder["dateiname"][1].get() or DEFAULT_TEMPLATE["dateiname"]
        self.lbl_beispiel.configure(text=f"Beispiel: {safe_filename(render(muster, ctx, gender))}.pdf")

    # ------------------------------------------------------------------ Bilder
    def _zeige_bild(self, slot):
        info = self.bilder[slot]
        name = info["vars"]["datei"].get()
        path = self.store.image_path(name)
        lbl = info["vorschau"]
        if not path:
            lbl.configure(image="", text="(kein Bild)")
            self._thumbs.pop(slot, None)
            return
        try:
            from PIL import Image, ImageTk

            img = Image.open(path)
            img.thumbnail((160, 70))
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, "white")
                img = img.convert("RGBA")
                bg.paste(img, mask=img.split()[-1])
                img = bg
            photo = ImageTk.PhotoImage(img)
            self._thumbs[slot] = photo
            lbl.configure(image=photo, text="")
        except Exception:  # noqa: BLE001 – Vorschau ist nur Komfort
            lbl.configure(image="", text=name)

    def _bild_waehlen(self, slot):
        path = filedialog.askopenfilename(parent=self, title=f"{BILD_TITEL[slot]} wählen",
                                          filetypes=[("Bilder", "*.png *.jpg *.jpeg"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            from PIL import Image

            with Image.open(path) as im:
                im.verify()
        except Exception:  # noqa: BLE001
            messagebox.showerror("Bild", "Die Datei ist kein lesbares Bild (PNG oder JPG).", parent=self)
            return
        name = self.store.import_image(slot, Path(path))
        self.bilder[slot]["vars"]["datei"].set(name)
        self._zeige_bild(slot)
        self.lbl_status.configure(text="Bild übernommen – bitte speichern.", style="Info.TLabel")

    def _bild_entfernen(self, slot):
        self.bilder[slot]["vars"]["datei"].set("")
        self._zeige_bild(slot)

    # ------------------------------------------------------------------ Aktionen
    def _einfuegen(self, tree):
        sel = tree.selection()
        if not sel:
            return
        platzhalter = tree.item(sel[0], "values")[0]
        w = self._fokus
        if w is None:
            messagebox.showinfo("Platzhalter", "Bitte zuerst in das Feld klicken, in das der "
                                "Platzhalter eingefügt werden soll.", parent=self)
            return
        w.insert("insert", platzhalter)
        w.focus_set()

    def _vorschau(self):
        try:
            tpl = self._werte()
            path = vorschau(tpl, self.store.assets)
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Vorschau", str(err), parent=self)
            return
        open_path(path)
        unbekannt = unknown_placeholders(tpl)
        if unbekannt:
            self.lbl_status.configure(text="Unbekannte Platzhalter: " + ", ".join(unbekannt),
                                      style="Fehler.TLabel")

    def _export(self):
        if self.ist_geaendert() and not self.verlassen():
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Vorlage exportieren", defaultextension=".einsatzvorlage",
            initialfile="Vorlage.einsatzvorlage",
            filetypes=[("Vorlage für Einsatzbescheinigung", "*.einsatzvorlage")])
        if path:
            self.store.export_template(Path(path))
            messagebox.showinfo("Export", "Vorlage samt Bildern gespeichert. Die Datei kann auf einem "
                                "anderen Rechner über „Vorlage importieren“ eingelesen werden.\n\n"
                                "Hinweis: Sie enthält die Unterschrift – bitte nur vertraulich weitergeben.",
                                parent=self)

    def _import(self):
        path = filedialog.askopenfilename(
            parent=self, title="Vorlage importieren",
            filetypes=[("Vorlage für Einsatzbescheinigung", "*.einsatzvorlage *.json"), ("Alle Dateien", "*.*")])
        if not path:
            return
        if not messagebox.askyesno("Vorlage importieren", "Die aktuelle Vorlage wird ersetzt. Fortfahren?",
                                   parent=self):
            return
        try:
            self.store.import_template(Path(path))
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Import", f"Die Vorlage konnte nicht gelesen werden:\n{err}", parent=self)
            return
        self.lade()
        self.lbl_status.configure(text="Vorlage importiert.", style="Ok.TLabel")

    def _standard(self):
        if not messagebox.askyesno("Standardtexte", "Alle Texte auf die Beispielvorlage „Löschzug 1, "
                                   "Feuerwehr Musterstadt“ zurücksetzen? Bilder und Positionen bleiben "
                                   "erhalten.\n\nTipp: Die eigene Vorlage vorher über „Vorlage "
                                   "exportieren“ sichern.", parent=self):
            return
        for key, (art, var, w) in self.felder.items():
            val = DEFAULT_TEMPLATE.get(key, "")
            if art == "entry":
                var.set(val)
            else:
                text_set(w, val)
        self.lbl_status.configure(text="Standardtexte eingesetzt – bitte speichern.", style="Info.TLabel")
