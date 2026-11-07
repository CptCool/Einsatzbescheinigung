"""Hauptbereich: Einsatz erfassen → Zeiten je Kamerad prüfen → PDFs + E-Mail-Entwürfe."""

import queue
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from .generator import Einsatz, Teilnahme, einsatz_ordner, erzeuge, unknown_placeholders
from .mailer import Entwurf, Mailer, programm_name
from .paths import open_path
from .placeholders import combine, fmt_date, fmt_duration, fmt_time, parse_date
from .verlauf import (anzeige_name, belegte_namen, eintragen, erstelle_sammel, finde,
                      kontakt_schluessel, lese_zeit, teilnehmer)
from .widgets import ScrollFrame, center_on, text_widget

HAKEN_AN, HAKEN_AUS = "☑", "☐"
SPALTEN_NEU = ("sel", "name", "dg", "mail")
SPALTEN_GESPEICHERT = ("sel", "name", "dg", "mail", "status")

_anzeige_name = anzeige_name


def _erstellt_am(t: dict) -> str:
    try:
        return datetime.fromisoformat(t.get("erstellt", "")).strftime("%d.%m.%Y")
    except ValueError:
        return ""


class EinsatzTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.store = app.store
        self.auswahl: set[str] = set()
        self.anpassungen: dict[str, dict] = {}
        self._basis = None
        self._basis_key = None
        self._treffer: dict | None = None  # gespeicherter Einsatz mit gleicher Nummer + Beginn
        self._reihenfolge: list[str] = []
        self._ende_manuell = False
        self._laeuft = False
        self._queue: queue.Queue = queue.Queue()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.seite1 = ttk.Frame(self)
        self.seite2 = ttk.Frame(self)
        for s in (self.seite1, self.seite2):
            s.grid(row=0, column=0, sticky="nsew")
        self._baue_seite1()
        self._baue_seite2()
        self.aktualisiere_liste()
        self.zeige_seite(1)

    # ================================================================== Seite 1
    def _baue_seite1(self):
        f = self.seite1
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)
        ttk.Label(f, text="Schritt 1 von 2 – Einsatz erfassen und Kameraden auswählen",
                  style="Titel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        box = ttk.LabelFrame(f, text="Einsatz", padding=(12, 8))
        box.grid(row=1, column=0, sticky="ew")
        heute = fmt_date(date.today())
        self.v_nummer = tk.StringVar()
        self.v_start_d, self.v_start_t = tk.StringVar(value=heute), tk.StringVar()
        self.v_end_d, self.v_end_t = tk.StringVar(value=heute), tk.StringVar()
        self.v_ausst = tk.StringVar(value=heute)

        pad = {"padx": (0, 8), "pady": 4}
        ttk.Label(box, text="Einsatznummer").grid(row=0, column=0, sticky="w", **pad)
        self.e_nummer = ttk.Entry(box, textvariable=self.v_nummer, width=20)
        self.e_nummer.grid(row=0, column=1, columnspan=2, sticky="w", **pad)
        ttk.Label(box, text="Beginn").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(box, textvariable=self.v_start_d, width=12).grid(row=1, column=1, sticky="w", **pad)
        self.e_start_t = ttk.Entry(box, textvariable=self.v_start_t, width=7)
        self.e_start_t.grid(row=1, column=2, sticky="w", **pad)
        ttk.Label(box, text="Uhr").grid(row=1, column=3, sticky="w", **pad)
        ttk.Label(box, text="Ende").grid(row=2, column=0, sticky="w", **pad)
        self.e_end_d = ttk.Entry(box, textvariable=self.v_end_d, width=12)
        self.e_end_d.grid(row=2, column=1, sticky="w", **pad)
        ttk.Entry(box, textvariable=self.v_end_t, width=7).grid(row=2, column=2, sticky="w", **pad)
        ttk.Label(box, text="Uhr").grid(row=2, column=3, sticky="w", **pad)

        ttk.Separator(box, orient="vertical").grid(row=0, column=4, rowspan=3, sticky="ns", padx=18)
        ttk.Label(box, text="Ausstellungsdatum").grid(row=0, column=5, sticky="w", **pad)
        ttk.Entry(box, textvariable=self.v_ausst, width=12).grid(row=0, column=6, sticky="w", **pad)
        self.lbl_dauer = ttk.Label(box, text="")
        self.lbl_dauer.grid(row=1, column=5, columnspan=2, sticky="w", **pad)
        ttk.Label(box, text="Datum TT.MM.JJJJ · Uhrzeit HH:MM (auch 1159)",
                  style="Hinweis.TLabel").grid(row=2, column=5, columnspan=2, sticky="w", **pad)

        self.v_start_d.trace_add("write", self._start_datum_geaendert)
        for v in (self.v_start_t, self.v_end_d, self.v_end_t):
            v.trace_add("write", lambda *_: self._zeige_dauer())
        for v in (self.v_nummer, self.v_start_t):
            v.trace_add("write", lambda *_: self._pruefe_gespeichert())
        self.e_end_d.bind("<Key>", lambda _e: setattr(self, "_ende_manuell", True))

        # Hinweis, wenn dieser Einsatz schon gespeichert ist (Nachtragen)
        self.banner = ttk.Frame(f, padding=(2, 8, 2, 0))
        self.banner.grid(row=2, column=0, sticky="ew")
        self.banner.columnconfigure(0, weight=1)
        self.lbl_banner = ttk.Label(self.banner, text="", style="Info.TLabel", wraplength=780,
                                    justify="left")
        self.lbl_banner.grid(row=0, column=0, sticky="w")
        ttk.Button(self.banner, text="Neuer Einsatz", command=self._neuer_einsatz).grid(
            row=0, column=1, sticky="e", padx=(10, 0))
        self.banner.grid_remove()

        # Kameradenliste
        box2 = ttk.LabelFrame(f, text="Kameraden", padding=(12, 8))
        box2.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        box2.columnconfigure(0, weight=1)
        box2.rowconfigure(1, weight=1)
        bar = ttk.Frame(box2)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(bar, text="Suchen").pack(side="left")
        self.v_filter = tk.StringVar()
        self.v_filter.trace_add("write", lambda *_: self.aktualisiere_liste())
        ttk.Entry(bar, textvariable=self.v_filter, width=24).pack(side="left", padx=(6, 12))
        ttk.Button(bar, text="Alle auswählen", command=self._alle).pack(side="left")
        ttk.Button(bar, text="Auswahl aufheben", command=self._keine).pack(side="left", padx=6)
        self.lbl_anzahl = ttk.Label(bar, text="", style="Fett.TLabel")
        self.lbl_anzahl.pack(side="right")

        self.tree = ttk.Treeview(box2, columns=SPALTEN_GESPEICHERT, show="headings",
                                 selectmode="none", displaycolumns=SPALTEN_NEU)
        for col, text, width, anchor, stretch in (
                ("sel", HAKEN_AN, 46, "center", False), ("name", "Name", 240, "w", True),
                ("dg", "Dienstgrad", 110, "w", False), ("mail", "E-Mail", 280, "w", True),
                ("status", "Bescheinigung", 170, "w", False)):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch)
        self.tree.heading("sel", command=self._alle_umschalten)
        self.tree.tag_configure("an", background="#e4f3e2")
        self.tree.tag_configure("ohne_mail", foreground="#b00020")
        vsb = ttk.Scrollbar(box2, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self._klick)
        self.tree.bind("<space>", self._leertaste)
        self.lbl_leer = ttk.Label(box2, text="Noch keine Kontakte vorhanden.\nBitte im Bereich "
                                  "„Kontakte“ anlegen oder aus einer CSV-/Excel-Datei importieren.",
                                  justify="center", style="Hinweis.TLabel")

        unten = ttk.Frame(f)
        unten.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(unten, text="Neuer Einsatz (Felder leeren)", command=self._neuer_einsatz).pack(side="left")
        ttk.Button(unten, text="Gespeicherte Einsätze …",
                   command=lambda: self.app.zeige_verlauf()).pack(side="left", padx=6)
        ttk.Button(unten, text="Weiter: Zeiten prüfen  →", style="Primar.TButton",
                   command=self._weiter).pack(side="right")

    def _start_datum_geaendert(self, *_):
        if not self._ende_manuell:
            self.v_end_d.set(self.v_start_d.get())
        self._zeige_dauer()
        self._pruefe_gespeichert()

    def _lese_einsatzzeit(self, korrigieren=False):
        start = combine(self.v_start_d.get(), self.v_start_t.get())
        end = combine(self.v_end_d.get(), self.v_end_t.get())
        folgetag = False
        if end <= start and self.v_end_d.get().strip() == self.v_start_d.get().strip():
            end += timedelta(days=1)
            folgetag = True
            if korrigieren:
                self._ende_manuell = True
                self.v_end_d.set(fmt_date(end))
        return start, end, folgetag

    def _zeige_dauer(self):
        try:
            start, end, folgetag = self._lese_einsatzzeit()
        except ValueError:
            self.lbl_dauer.configure(text="")
            return
        if end <= start:
            self.lbl_dauer.configure(text="Ende liegt vor dem Beginn", style="Fehler.TLabel")
            return
        extra = " · Ende am Folgetag" if folgetag else ""
        self.lbl_dauer.configure(text=f"Dauer: {fmt_duration(end - start)}{extra}", style="Info.TLabel")

    def _pruefe_gespeichert(self):
        """Ist ein Einsatz mit dieser Nummer und diesem Beginn schon gespeichert?"""
        if not hasattr(self, "tree"):
            return
        try:
            start = combine(self.v_start_d.get(), self.v_start_t.get())
            rec = finde(self.store.einsaetze, self.v_nummer.get(), start)
        except ValueError:
            rec = None
        self._treffer = rec
        if rec:
            n = len(rec.get("teilnehmer", []))
            self.lbl_banner.configure(text=(
                f"Dieser Einsatz ist bereits gespeichert: {n} Kamerad{'en haben' if n != 1 else ' hat'} "
                "schon eine Bescheinigung (✓ in der Liste). Wähle die Kameraden aus, die ergänzt "
                "werden sollen – die vorhandenen Bescheinigungen bleiben erhalten."))
            self.banner.grid()
            self.tree.configure(displaycolumns=SPALTEN_GESPEICHERT)
        else:
            self.banner.grid_remove()
            self.tree.configure(displaycolumns=SPALTEN_NEU)
        for cid in self.tree.get_children():
            self.tree.set(cid, "status", self._status_text(cid))

    def _status_text(self, cid: str) -> str:
        t = teilnehmer(self._treffer).get(cid)
        return f"✓ erstellt am {_erstellt_am(t)}" if t else ""

    def aktualisiere_liste(self):
        """Kontaktliste neu aufbauen (z. B. nach Änderungen im Bereich „Kontakte“)."""
        ids = {c["id"] for c in self.store.contacts}
        self.auswahl &= ids
        filt = self.v_filter.get().strip().casefold() if hasattr(self, "v_filter") else ""
        self.tree.delete(*self.tree.get_children())
        for c in self.store.contacts:
            text = f"{c['vorname']} {c['nachname']} {c['dienstgrad']} {c['email']}".casefold()
            if filt and filt not in text:
                continue
            self._zeile_einfuegen(c)
        if self.store.contacts:
            self.lbl_leer.place_forget()
        else:
            self.lbl_leer.place(in_=self.tree, relx=0.5, rely=0.4, anchor="center")
        self._zaehle()

    def _zeile_einfuegen(self, c):
        an = c["id"] in self.auswahl
        tags = ["an"] if an else []
        if not c["email"]:
            tags.append("ohne_mail")
        self.tree.insert("", "end", iid=c["id"], tags=tags, values=(
            HAKEN_AN if an else HAKEN_AUS, _anzeige_name(c), c["dienstgrad"],
            c["email"] or "– keine E-Mail –", self._status_text(c["id"])))

    def _setze(self, cid, an: bool):
        if an:
            self.auswahl.add(cid)
        else:
            self.auswahl.discard(cid)
        if self.tree.exists(cid):
            c = self.store.contact_by_id(cid)
            tags = ["an"] if an else []
            if c and not c["email"]:
                tags.append("ohne_mail")
            self.tree.item(cid, tags=tags)
            self.tree.set(cid, "sel", HAKEN_AN if an else HAKEN_AUS)

    def _klick(self, event):
        if self.tree.identify_region(event.x, event.y) in ("cell", "tree"):
            cid = self.tree.identify_row(event.y)
            if cid:
                self._setze(cid, cid not in self.auswahl)
                self.tree.focus(cid)
                self.tree.focus_set()
                self._zaehle()
                return "break"
        return None

    def _leertaste(self, _event):
        cid = self.tree.focus()
        if cid:
            self._setze(cid, cid not in self.auswahl)
            self._zaehle()
        return "break"

    def _alle(self):
        for cid in self.tree.get_children():
            self._setze(cid, True)
        self._zaehle()

    def _keine(self):
        for cid in list(self.auswahl):
            self._setze(cid, False)
        self._zaehle()

    def _alle_umschalten(self):
        sichtbar = self.tree.get_children()
        if sichtbar and all(cid in self.auswahl for cid in sichtbar):
            for cid in sichtbar:
                self._setze(cid, False)
        else:
            self._alle()
        self._zaehle()

    def _zaehle(self):
        n, gesamt = len(self.auswahl), len(self.store.contacts)
        self.lbl_anzahl.configure(text=f"{n} von {gesamt} ausgewählt")

    def _neuer_einsatz(self):
        heute = fmt_date(date.today())
        self._ende_manuell = False
        self.v_nummer.set("")
        self.v_start_d.set(heute)
        self.v_start_t.set("")
        self.v_end_d.set(heute)
        self.v_end_t.set("")
        self.v_ausst.set(heute)
        self._keine()
        self.anpassungen.clear()
        self._basis = self._basis_key = None
        self.zeige_seite(1)
        self.fokus_nummer()

    def fokus_nummer(self):
        """Fokus sicher ins Feld Einsatznummer setzen.

        ``focus_force`` statt ``focus_set``: Unter macOS bleibt die Tastatur sonst nach dem
        Wechsel aus dem Mailprogramm oder nach einem Dialog gelegentlich beim alten Fenster,
        und die Einsatznummer lässt sich nicht eintippen.
        """
        def setzen():
            try:
                self.e_nummer.focus_force()
                self.e_nummer.icursor("end")
                self.e_nummer.select_range(0, "end")
            except tk.TclError:
                pass
        self.after_idle(setzen)

    def lade_einsatz(self, rec: dict):
        """Gespeicherten Einsatz übernehmen, um weitere Kameraden zu ergänzen."""
        if self._laeuft:
            messagebox.showinfo("Bitte warten", "Es werden gerade noch E-Mail-Entwürfe erstellt.",
                                parent=self)
            return
        start, end = lese_zeit(rec["start"]), lese_zeit(rec["ende"])
        self._ende_manuell = True
        self.v_nummer.set(rec.get("nummer", ""))
        self.v_start_d.set(fmt_date(start))
        self.v_start_t.set(fmt_time(start))
        self.v_end_d.set(fmt_date(end))
        self.v_end_t.set(fmt_time(end))
        self.v_ausst.set(fmt_date(date.today()))
        self.v_filter.set("")
        self._keine()
        self.anpassungen.clear()
        self._basis = self._basis_key = None
        self._pruefe_gespeichert()
        self.zeige_seite(1)

    def _weiter(self):
        try:
            start, end, _ = self._lese_einsatzzeit(korrigieren=True)
            parse_date(self.v_ausst.get())
        except ValueError as err:
            messagebox.showerror("Bitte prüfen", str(err), parent=self)
            return
        if end <= start:
            messagebox.showerror("Bitte prüfen", "Das Einsatzende liegt vor dem Beginn.", parent=self)
            return
        if end - start > timedelta(hours=24) and not messagebox.askyesno(
                "Langer Einsatz", f"Der Einsatz dauert {fmt_duration(end - start)}. Ist das richtig?",
                parent=self):
            return
        if not self.auswahl:
            messagebox.showinfo("Keine Auswahl", "Bitte mindestens einen Kameraden auswählen.",
                                parent=self)
            return
        if not self.v_nummer.get().strip() and not messagebox.askyesno(
                "Einsatznummer fehlt", "Es ist keine Einsatznummer eingetragen. Trotzdem fortfahren?",
                parent=self):
            return
        self._pruefe_gespeichert()
        rec = self._treffer
        key = (start, end, rec["id"] if rec else None)
        if key != self._basis_key:
            self.anpassungen.clear()
            self._basis_key = key
        self._basis = (start, end)
        kontakte = [c for c in self.store.contacts if c["id"] in self.auswahl]
        self._reihenfolge = [c["id"] for c in kontakte]
        fertig = teilnehmer(rec)
        for c in kontakte:
            if c["id"] not in self.anpassungen:
                t = fertig.get(c["id"])
                # bereits bescheinigt: gespeicherte Zeiten vorschlagen, sonst die Einsatzzeit
                self.anpassungen[c["id"]] = (self._zeiten(lese_zeit(t["start"]), lese_zeit(t["ende"]))
                                             if t else self._standardzeiten())
        self._baue_zeilen(kontakte)
        self.zeige_seite(2)

    def _standardzeiten(self) -> dict:
        return self._zeiten(*self._basis)

    @staticmethod
    def _zeiten(start: datetime, end: datetime) -> dict:
        return {"sd": fmt_date(start), "st": fmt_time(start), "ed": fmt_date(end), "et": fmt_time(end)}

    def _zielordner(self, rec: dict | None, nummer: str, start: datetime) -> Path:
        """Beim Ergänzen der Ordner des gespeicherten Einsatzes, sonst ein neuer Ordner."""
        if rec and Path(rec.get("ordner", "")).is_dir():
            return Path(rec["ordner"])
        return einsatz_ordner(self.store.output_dir(), Einsatz(nummer, start, start, date.today()))

    # ================================================================== Seite 2
    def _baue_seite2(self):
        f = self.seite2
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)
        ttk.Label(f, text="Schritt 2 von 2 – Zeiten je Kamerad prüfen und Bescheinigungen erstellen",
                  style="Titel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.lbl_einsatz = ttk.Label(f, text="")
        self.lbl_einsatz.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.sf = ScrollFrame(f)
        self.sf.grid(row=2, column=0, sticky="nsew")

        opt = ttk.LabelFrame(f, text="Ausgabe", padding=(12, 8))
        opt.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        opt.columnconfigure(1, weight=1)
        self.v_mails = tk.BooleanVar(value=True)
        self.v_sammel = tk.BooleanVar(value=True)
        self.cb_mails = ttk.Checkbutton(opt, text="E-Mail-Entwürfe erstellen", variable=self.v_mails)
        self.cb_mails.grid(row=0, column=0, sticky="w")
        self.lbl_prog = ttk.Label(opt, text="", style="Hinweis.TLabel")
        self.lbl_prog.grid(row=0, column=1, sticky="w", padx=10)
        self.cb_sammel = ttk.Checkbutton(opt, text="Sammel-PDF für die Ablage erstellen",
                                         variable=self.v_sammel)
        self.cb_sammel.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.lbl_ordner = ttk.Label(opt, text="", style="Hinweis.TLabel")
        self.lbl_ordner.grid(row=1, column=1, sticky="w", padx=10, pady=(4, 0))

        self.fortschritt = ttk.Frame(f)
        self.fortschritt.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.fortschritt.columnconfigure(0, weight=1)
        self.pb = ttk.Progressbar(self.fortschritt, mode="determinate")
        self.lbl_status = ttk.Label(self.fortschritt, text="")

        unten = ttk.Frame(f)
        unten.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.btn_zurueck = ttk.Button(unten, text="←  Zurück", command=lambda: self.zeige_seite(1))
        self.btn_zurueck.pack(side="left")
        self.btn_erstellen = ttk.Button(unten, text="PDFs erstellen und E-Mails vorbereiten",
                                        style="Primar.TButton", command=self._erstellen)
        self.btn_erstellen.pack(side="right")

    def _baue_zeilen(self, kontakte):
        inner = self.sf.inner
        for child in inner.winfo_children():
            child.destroy()
        self._zeilen = {}
        kopf = [("Kamerad", 0, 1), ("Beginn (Datum · Uhrzeit)", 1, 2), ("Ende (Datum · Uhrzeit)", 3, 2),
                ("Dauer", 5, 1)]
        for text, col, span in kopf:
            ttk.Label(inner, text=text, style="Fett.TLabel").grid(
                row=0, column=col, columnspan=span, sticky="w", padx=(4, 8), pady=(2, 6))
        inner.columnconfigure(0, weight=1)
        rec = self._treffer
        fertig = teilnehmer(rec)
        for r, c in enumerate(kontakte, start=1):
            cid = c["id"]
            werte = self.anpassungen[cid]
            vars_ = {k: tk.StringVar(value=v) for k, v in werte.items()}
            name = _anzeige_name(c) + (f"  ({c['dienstgrad']})" if c["dienstgrad"] else "")
            ttk.Label(inner, text=name).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=3)
            for col, key, width in ((1, "sd", 11), (2, "st", 6), (3, "ed", 11), (4, "et", 6)):
                ttk.Entry(inner, textvariable=vars_[key], width=width).grid(
                    row=r, column=col, sticky="w", padx=(0, 6), pady=3)
            lbl = ttk.Label(inner, text="", width=22)
            lbl.grid(row=r, column=5, sticky="w", padx=(4, 4))
            ttk.Button(inner, text="↺", width=3, command=lambda i=cid: self._zuruecksetzen(i)).grid(
                row=r, column=6, padx=(0, 6))
            hinweise = ([] if c["email"] else ["keine E-Mail"]) + (
                ["wird neu erstellt"] if cid in fertig else [])
            ttk.Label(inner, text=" · ".join(hinweise),
                      style="Info.TLabel" if c["email"] else "Fehler.TLabel").grid(
                row=r, column=7, sticky="w")
            self._zeilen[cid] = (vars_, lbl)
            for key, var in vars_.items():
                var.trace_add("write", lambda *_a, i=cid: self._zeile_geaendert(i))
            self._zeile_geaendert(cid)
        self.sf.to_top()

        start, end = self._basis
        nummer = self.v_nummer.get().strip()
        teile = [f"Einsatz {nummer}" if nummer else "Einsatz ohne Nummer",
                 f"{fmt_date(start)} {fmt_time(start)} – "
                 f"{fmt_time(end) if start.date() == end.date() else fmt_date(end) + ' ' + fmt_time(end)} Uhr",
                 f"{len(kontakte)} Kamerad{'en' if len(kontakte) != 1 else ''}"]
        if rec:
            teile.append(f"Ergänzung – {len(fertig)} bereits bescheinigt")
        self.lbl_einsatz.configure(text="  ·  ".join(teile) +
                                   "   –   Abweichende Zeiten einfach überschreiben; ↺ stellt die Einsatzzeit wieder her.")
        settings = self.store.settings
        self.v_mails.set(bool(settings.get("mails_erstellen", True)))
        self.v_sammel.set(bool(settings.get("sammel_pdf", True)))
        self.lbl_prog.configure(text=f"mit: {programm_name(settings.get('mailprogramm', 'auto'))}")
        bcc = self.store.bcc_list()
        if bcc:
            self.lbl_prog.configure(text=self.lbl_prog.cget("text") + f" · Kopie (BCC) an {', '.join(bcc)}")
        self.lbl_ordner.configure(text=f"Speicherort: {self._zielordner(rec, nummer, start)}")
        self.cb_sammel.configure(text="Sammel-PDF für die Ablage aktualisieren (alle Kameraden)"
                                 if rec else "Sammel-PDF für die Ablage erstellen")

    def _zeile_geaendert(self, cid):
        vars_, lbl = self._zeilen[cid]
        werte = {k: v.get() for k, v in vars_.items()}
        self.anpassungen[cid] = werte
        try:
            s = combine(werte["sd"], werte["st"])
            e = combine(werte["ed"], werte["et"])
        except ValueError:
            lbl.configure(text="ungültige Eingabe", style="Fehler.TLabel")
            return
        if e <= s:
            lbl.configure(text="Ende vor Beginn", style="Fehler.TLabel")
            return
        angepasst = werte != self._standardzeiten()
        lbl.configure(text=fmt_duration(e - s) + ("  · angepasst" if angepasst else ""),
                      style="Info.TLabel" if angepasst else "TLabel")

    def _zuruecksetzen(self, cid):
        vars_, _ = self._zeilen[cid]
        for k, v in self._standardzeiten().items():
            vars_[k].set(v)

    def zeige_seite(self, n: int):
        (self.seite1 if n == 1 else self.seite2).tkraise()

    # ================================================================== Erstellen
    def _erstellen(self):
        if self._laeuft:
            return
        store = self.store
        if self.app.vorlage.ist_geaendert() and not self.app.vorlage.verlassen():
            return
        unbekannt = unknown_placeholders(store.template)
        if unbekannt and not messagebox.askyesno(
                "Unbekannte Platzhalter",
                "Die Vorlage enthält Platzhalter, die nicht ersetzt werden können:\n\n"
                + ", ".join(unbekannt) + "\n\nTrotzdem fortfahren?", parent=self):
            return

        teilnahmen, fehler = [], []
        for cid in self._reihenfolge:
            c = store.contact_by_id(cid)
            if not c:
                continue
            w = self.anpassungen[cid]
            try:
                s, e = combine(w["sd"], w["st"]), combine(w["ed"], w["et"])
            except ValueError as err:
                fehler.append(f"{_anzeige_name(c)}: {err}")
                continue
            if e <= s:
                fehler.append(f"{_anzeige_name(c)}: Das Ende liegt nicht nach dem Beginn.")
                continue
            teilnahmen.append(Teilnahme(c, s, e))
        if fehler:
            messagebox.showerror("Bitte Zeiten prüfen", "\n".join(fehler), parent=self)
            return

        mails = self.v_mails.get()
        ohne = [_anzeige_name(t.contact) for t in teilnahmen if not t.contact["email"]]
        if mails and ohne and not messagebox.askyesno(
                "E-Mail-Adresse fehlt",
                "Für folgende Kameraden ist keine E-Mail-Adresse hinterlegt:\n\n• " + "\n• ".join(ohne)
                + "\n\nDie PDFs werden trotzdem erstellt, es gibt aber keinen E-Mail-Entwurf. "
                  "Fortfahren?", parent=self):
            return

        start, end = self._basis
        nummer = self.v_nummer.get().strip()
        try:
            einsatz = Einsatz(nummer, start, end, parse_date(self.v_ausst.get()))
        except ValueError as err:
            messagebox.showerror("Bitte prüfen", f"Ausstellungsdatum: {err}", parent=self)
            return
        rec = finde(store.einsaetze, nummer, start)
        neu = {kontakt_schluessel(t.contact) for t in teilnahmen}
        try:
            ergebnisse, ordner = erzeuge(einsatz, teilnahmen, store.template, store.assets,
                                         self._zielordner(rec, nummer, start), belegte_namen(rec, neu))
        except PermissionError as err:
            messagebox.showerror("Datei gesperrt", "Eine Datei konnte nicht geschrieben werden – ist "
                                 f"sie noch in einem PDF-Programm geöffnet?\n\n{err}", parent=self)
            return
        except Exception as err:  # noqa: BLE001 – dem Nutzer jeden Fehler zeigen
            messagebox.showerror("Fehler beim Erstellen der PDFs", str(err), parent=self)
            return

        # Einsatz speichern, damit später weitere Kameraden ergänzt werden können
        ergaenzt = rec is not None
        hinweise = []
        rec = eintragen(rec, einsatz, ergebnisse, ordner)
        try:
            store.upsert_einsatz(rec)
        except OSError as err:
            hinweise.append(f"Der Einsatz konnte nicht gespeichert werden: {err}")
        sammel = None
        if self.v_sammel.get():
            try:
                sammel, fehlen = erstelle_sammel(rec)
                if fehlen:
                    hinweise.append("Nicht im Sammel-PDF, weil die Datei nicht mehr im Ordner liegt: "
                                    + ", ".join(fehlen))
            except PermissionError:
                hinweise.append("Das Sammel-PDF konnte nicht geschrieben werden – ist es noch in "
                                "einem PDF-Programm geöffnet?")
            except Exception as err:  # noqa: BLE001
                hinweise.append(f"Sammel-PDF fehlgeschlagen: {err}")
        self._keine()  # die Kameraden stehen jetzt als „✓ erstellt“ in der Liste
        self.app.einsaetze_geaendert()

        self._ergebnis = {"ordner": ordner, "sammel": sammel, "zeilen": [], "hinweise": hinweise,
                          "ergaenzt": ergaenzt, "gesamt": len(rec["teilnehmer"])}
        if not mails:
            for erg in ergebnisse:
                self._ergebnis["zeilen"].append((_anzeige_name(erg.contact), True, "PDF erstellt"))
            self._fertig()
            return

        entwuerfe = []
        for erg in ergebnisse:
            if erg.contact["email"]:
                entwuerfe.append((erg, Entwurf(erg.contact["email"], erg.betreff, erg.text,
                                               [erg.pdf], store.bcc_list())))
            else:
                self._ergebnis["zeilen"].append(
                    (_anzeige_name(erg.contact), False, "PDF erstellt · kein Entwurf (keine E-Mail-Adresse)"))
        self._starte_mails(entwuerfe, ordner)

    def _starte_mails(self, entwuerfe, ordner):
        self._laeuft = True
        self.btn_erstellen.state(["disabled"])
        self.btn_zurueck.state(["disabled"])
        self.pb.configure(maximum=max(1, len(entwuerfe)), value=0)
        self.pb.grid(row=0, column=0, sticky="ew")
        self.lbl_status.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.lbl_status.configure(text="E-Mail-Entwürfe werden vorbereitet …")
        programm = self.store.settings.get("mailprogramm", "auto")

        def arbeit():
            mailer = Mailer(programm, ordner)
            for i, (erg, entwurf) in enumerate(entwuerfe):
                name = _anzeige_name(erg.contact)
                self._queue.put(("status", i, f"Entwurf für {name} ({i + 1}/{len(entwuerfe)}) …"))
                try:
                    info = mailer.erstelle(entwurf)
                    self._queue.put(("ok", i, (name, True, f"PDF erstellt · {info}")))
                except Exception as err:  # noqa: BLE001
                    self._queue.put(("fehler", i, (name, False, f"PDF erstellt · Entwurf fehlgeschlagen: {err}")))
            self._queue.put(("ende", None, None))

        threading.Thread(target=arbeit, daemon=True).start()
        self.after(100, self._pruefe_queue)

    def _pruefe_queue(self):
        try:
            while True:
                art, i, daten = self._queue.get_nowait()
                if art == "status":
                    self.lbl_status.configure(text=daten)
                elif art in ("ok", "fehler"):
                    self._ergebnis["zeilen"].append(daten)
                    self.pb.configure(value=i + 1)
                elif art == "ende":
                    self._laeuft = False
                    self.btn_erstellen.state(["!disabled"])
                    self.btn_zurueck.state(["!disabled"])
                    self.pb.grid_remove()
                    self.lbl_status.grid_remove()
                    self._fertig()
                    return
        except queue.Empty:
            pass
        self.after(100, self._pruefe_queue)

    def _fertig(self):
        ErgebnisDialog(self, self._ergebnis, self.v_mails.get())


class ErgebnisDialog(tk.Toplevel):
    def __init__(self, tab: EinsatzTab, ergebnis: dict, mails: bool):
        super().__init__(tab)
        self.tab = tab
        self.title("Fertig")
        self.transient(tab.winfo_toplevel())
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        zeilen = sorted(ergebnis["zeilen"], key=lambda z: z[0].casefold())
        ok = sum(1 for z in zeilen if z[1])
        titel = f"{len(zeilen)} Bescheinigung{'en' if len(zeilen) != 1 else ''} erstellt"
        if ergebnis.get("ergaenzt"):
            titel += f" – der Einsatz hat jetzt {ergebnis['gesamt']} Bescheinigungen"
        ttk.Label(frame, text=titel, style="Titel.TLabel").pack(anchor="w")
        if mails:
            ttk.Label(frame, text=f"{ok} E-Mail-Entwurf/Entwürfe vorbereitet. Die E-Mails wurden NICHT "
                      "gesendet – bitte jeden Entwurf prüfen und selbst auf „Senden“ klicken.",
                      wraplength=560, style="Info.TLabel").pack(anchor="w", pady=(6, 10))
        txt = text_widget(frame, height=min(14, max(4, len(zeilen) + 1)), width=80)
        txt.pack(fill="both", expand=True)
        for name, gut, info in zeilen:
            txt.insert("end", f"{'✓' if gut else '⚠'}  {name}: {info}\n")
        for hinweis in ergebnis.get("hinweise", []):
            txt.insert("end", f"⚠  {hinweis}\n")
        txt.insert("end", f"\nOrdner: {ergebnis['ordner']}\n")
        if ergebnis.get("sammel"):
            txt.insert("end", f"Sammel-PDF: {ergebnis['sammel'].name} "
                              f"({ergebnis['gesamt']} Bescheinigung{'en' if ergebnis['gesamt'] != 1 else ''})\n")
        txt.insert("end", "\nDer Einsatz ist gespeichert. Vergessene Kameraden lassen sich jederzeit "
                          "über „Weitere Kameraden ergänzen“ oder „Gespeicherte Einsätze“ nachtragen.\n")
        txt.configure(state="disabled")

        knoepfe = ttk.Frame(frame)
        knoepfe.pack(fill="x", pady=(12, 0))
        ttk.Button(knoepfe, text="Ordner öffnen",
                   command=lambda: open_path(ergebnis["ordner"])).pack(side="left")
        if ergebnis.get("sammel"):
            ttk.Button(knoepfe, text="Sammel-PDF öffnen",
                       command=lambda: open_path(ergebnis["sammel"])).pack(side="left", padx=6)
        ttk.Button(knoepfe, text="Schließen", command=self._schliessen).pack(side="right")
        ttk.Button(knoepfe, text="Weitere Kameraden ergänzen",
                   command=lambda: self._schliessen(lambda: tab.zeige_seite(1))).pack(side="right", padx=6)
        ttk.Button(knoepfe, text="Neuer Einsatz",
                   command=lambda: self._schliessen(tab._neuer_einsatz)).pack(side="right")
        center_on(self, tab.winfo_toplevel())
        self.lift()
        self.focus_set()

    def _schliessen(self, danach=None):
        """Dialog schließen und die Tastatur zuverlässig an das Hauptfenster zurückgeben."""
        top = self.tab.winfo_toplevel()
        self.destroy()
        try:
            top.focus_force()
        except tk.TclError:
            pass
        if danach:
            danach()
