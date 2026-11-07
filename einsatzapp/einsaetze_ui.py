"""Bereich „Gespeicherte Einsätze“: erstellte Einsätze ansehen und Kameraden nachtragen."""

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .paths import open_path
from .placeholders import fmt_date, fmt_time
from .verlauf import anzeige_name, lese_zeit, pdf_pfad, sammel_pfad


def _zeitraum(start: datetime, end: datetime) -> str:
    ende = fmt_time(end) if start.date() == end.date() else f"{fmt_date(end)} {fmt_time(end)}"
    return f"{fmt_time(start)} – {ende}"


def _zeitstempel(text: str) -> str:
    try:
        return datetime.fromisoformat(text).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


class EinsaetzeTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.store = app.store
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=3)
        self.rowconfigure(4, weight=2)

        ttk.Label(self, text="Gespeicherte Einsätze", style="Titel.TLabel").grid(
            row=0, column=0, sticky="w")
        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        ttk.Label(bar, text="Jeder erstellte Einsatz wird hier gespeichert. Wurde ein Kamerad "
                  "vergessen: Einsatz wählen und „Kameraden ergänzen“.",
                  style="Hinweis.TLabel").pack(side="left")
        self.v_filter = tk.StringVar()
        self.v_filter.trace_add("write", lambda *_: self.aktualisiere())
        ttk.Entry(bar, textvariable=self.v_filter, width=22).pack(side="right")
        ttk.Label(bar, text="Suchen").pack(side="right", padx=(0, 6))

        oben = ttk.Frame(self)
        oben.grid(row=2, column=0, sticky="nsew")
        oben.columnconfigure(0, weight=1)
        oben.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(oben, columns=("datum", "zeit", "nummer", "anzahl", "geaendert"),
                                 show="headings", selectmode="browse")
        for col, text, width, stretch in (("datum", "Datum", 100, False), ("zeit", "Zeit", 150, False),
                                          ("nummer", "Einsatznummer", 200, True),
                                          ("anzahl", "Bescheinigungen", 120, False),
                                          ("geaendert", "Zuletzt erstellt", 150, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w", stretch=stretch)
        vsb = ttk.Scrollbar(oben, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._zeige_details())
        self.tree.bind("<Double-1>", lambda _e: self._ergaenzen())
        self.tree.bind("<Return>", lambda _e: self._ergaenzen())
        self.lbl_leer = ttk.Label(oben, text="Noch keine Einsätze gespeichert.\nSobald im Bereich "
                                  "„Einsatz“ Bescheinigungen erstellt werden, erscheint der Einsatz hier.",
                                  justify="center", style="Hinweis.TLabel")

        knoepfe = ttk.Frame(self)
        knoepfe.grid(row=3, column=0, sticky="ew", pady=(8, 8))
        self.btn_ergaenzen = ttk.Button(knoepfe, text="Kameraden ergänzen  →", style="Primar.TButton",
                                        command=self._ergaenzen)
        self.btn_ergaenzen.pack(side="right")
        self.btn_ordner = ttk.Button(knoepfe, text="Ordner öffnen", command=self._ordner)
        self.btn_ordner.pack(side="left")
        self.btn_sammel = ttk.Button(knoepfe, text="Sammel-PDF öffnen", command=self._sammel)
        self.btn_sammel.pack(side="left", padx=6)
        self.btn_entfernen = ttk.Button(knoepfe, text="Aus der Liste entfernen", command=self._entfernen)
        self.btn_entfernen.pack(side="left")

        unten = ttk.LabelFrame(self, text="Bescheinigte Kameraden", padding=(12, 8))
        unten.grid(row=4, column=0, sticky="nsew")
        unten.columnconfigure(0, weight=1)
        unten.rowconfigure(0, weight=1)
        self.details = ttk.Treeview(unten, columns=("name", "dg", "zeit", "ausgestellt", "pdf"),
                                    show="headings", selectmode="none", height=6)
        for col, text, width, stretch in (("name", "Name", 220, True), ("dg", "Dienstgrad", 90, False),
                                          ("zeit", "Einsatzzeit", 190, False),
                                          ("ausgestellt", "Erstellt", 140, False),
                                          ("pdf", "PDF", 120, False)):
            self.details.heading(col, text=text, anchor="w")
            self.details.column(col, width=width, anchor="w", stretch=stretch)
        self.details.tag_configure("fehlt", foreground="#b00020")
        vsb2 = ttk.Scrollbar(unten, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=vsb2.set)
        self.details.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")
        self.aktualisiere()

    # ------------------------------------------------------------------ Liste
    def aktualisiere(self, auswahl: str | None = None):
        auswahl = auswahl or self._auswahl_id()
        filt = self.v_filter.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())
        for rec in self.store.einsaetze:
            start, end = lese_zeit(rec["start"]), lese_zeit(rec["ende"])
            namen = " ".join(anzeige_name(t["kontakt"]) for t in rec.get("teilnehmer", []))
            if filt and filt not in f"{rec.get('nummer', '')} {fmt_date(start)} {namen}".casefold():
                continue
            self.tree.insert("", "end", iid=rec["id"], values=(
                fmt_date(start), _zeitraum(start, end), rec.get("nummer") or "– ohne Nummer –",
                len(rec.get("teilnehmer", [])), _zeitstempel(rec.get("geaendert"))))
        if self.store.einsaetze:
            self.lbl_leer.place_forget()
        else:
            self.lbl_leer.place(in_=self.tree, relx=0.5, rely=0.4, anchor="center")
        if auswahl and self.tree.exists(auswahl):
            self.tree.selection_set(auswahl)
            self.tree.see(auswahl)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        self._zeige_details()

    def zeige(self, eid: str):
        self.v_filter.set("")
        self.aktualisiere(eid)

    def _auswahl_id(self) -> str | None:
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return sel[0] if sel else None

    def _auswahl(self) -> dict | None:
        eid = self._auswahl_id()
        return self.store.einsatz_by_id(eid) if eid else None

    def _zeige_details(self):
        self.details.delete(*self.details.get_children())
        rec = self._auswahl()
        state = ["!disabled"] if rec else ["disabled"]
        for b in (self.btn_ergaenzen, self.btn_ordner, self.btn_entfernen):
            b.state(state)
        self.btn_sammel.state(["!disabled"] if rec and sammel_pfad(rec).is_file() else ["disabled"])
        if not rec:
            return
        for i, t in enumerate(rec.get("teilnehmer", [])):
            vorhanden = pdf_pfad(rec, t).is_file()
            self.details.insert("", "end", iid=str(i), tags=() if vorhanden else ("fehlt",), values=(
                anzeige_name(t["kontakt"]), t["kontakt"].get("dienstgrad", ""),
                f"{fmt_date(lese_zeit(t['start']))}  {_zeitraum(lese_zeit(t['start']), lese_zeit(t['ende']))}",
                _zeitstempel(t.get("erstellt")), "vorhanden" if vorhanden else "nicht im Ordner"))

    # ------------------------------------------------------------------ Aktionen
    def _ergaenzen(self):
        rec = self._auswahl()
        if rec:
            self.app.einsatz_ergaenzen(rec)

    def _ordner(self):
        rec = self._auswahl()
        if not rec:
            return
        ordner = Path(rec.get("ordner", ""))
        if ordner.is_dir():
            open_path(ordner)
        else:
            messagebox.showwarning("Ordner nicht gefunden", f"Der Ordner existiert nicht mehr:\n\n{ordner}",
                                   parent=self)

    def _sammel(self):
        rec = self._auswahl()
        if rec and sammel_pfad(rec).is_file():
            open_path(sammel_pfad(rec))

    def _entfernen(self):
        rec = self._auswahl()
        if not rec:
            return
        nummer = rec.get("nummer") or "ohne Nummer"
        if not messagebox.askyesno(
                "Aus der Liste entfernen",
                f"Einsatz {nummer} vom {fmt_date(lese_zeit(rec['start']))} aus der Liste entfernen?\n\n"
                "Die PDFs im Ablageordner bleiben erhalten. Danach lassen sich zu diesem Einsatz aber "
                "keine Kameraden mehr ergänzen.", parent=self, icon="warning"):
            return
        self.store.delete_einsatz(rec["id"])
        self.app.einsaetze_geaendert()
