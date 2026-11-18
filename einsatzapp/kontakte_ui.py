"""Bereich „Kontakte“: Kameraden anlegen, bearbeiten, importieren, exportieren."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .formulare import ANREDEN, DIENSTGRADE, EMAIL_RE
from .formulare import KONTAKT_FORMULAR as FELDER
from .importer import ZIELFELDER, auto_zuordnung, exportiere_csv, lese_tabelle, wende_an
from .widgets import center_on


class KontakteTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.store = app.store
        self.aktuell: str | None = None
        self._original: dict = {}
        self._ignoriere_auswahl = False
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Kontakte", style="Titel.TLabel").grid(row=0, column=0, sticky="w",
                                                                     pady=(0, 10))
        self._baue_liste()
        self._baue_formular()
        self.lade_liste()
        self._leeres_formular()

    # ------------------------------------------------------------------ Liste
    def _baue_liste(self):
        links = ttk.Frame(self)
        links.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        links.columnconfigure(0, weight=1)
        links.rowconfigure(2, weight=1)
        bar = ttk.Frame(links)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(bar, text="+ Neuer Kontakt", command=self._neu).pack(side="left")
        ttk.Button(bar, text="Löschen", command=self._loeschen).pack(side="left", padx=6)
        ttk.Button(bar, text="Exportieren (CSV) …", command=self._export).pack(side="right")
        ttk.Button(bar, text="Importieren (CSV/Excel) …", command=self._import).pack(side="right", padx=6)
        such = ttk.Frame(links)
        such.grid(row=1, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(such, text="Suchen").pack(side="left")
        self.v_filter = tk.StringVar()
        self.v_filter.trace_add("write", lambda *_: self.lade_liste())
        ttk.Entry(such, textvariable=self.v_filter, width=28).pack(side="left", padx=6)
        self.lbl_anzahl = ttk.Label(such, text="", style="Hinweis.TLabel")
        self.lbl_anzahl.pack(side="right")

        self.tree = ttk.Treeview(links, columns=("name", "dg", "mail", "ort"), show="headings",
                                 selectmode="browse")
        for col, text, width, stretch in (("name", "Name", 200, True), ("dg", "Dienstgrad", 90, False),
                                          ("mail", "E-Mail", 220, True), ("ort", "Ort", 110, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="w")
        vsb = ttk.Scrollbar(links, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=2, column=0, sticky="nsew")
        vsb.grid(row=2, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._auswahl)

    def lade_liste(self, waehle: str | None = None):
        filt = self.v_filter.get().strip().casefold()
        self._ignoriere_auswahl = True
        self.tree.delete(*self.tree.get_children())
        for c in self.store.contacts:
            hay = " ".join(c.values()).casefold()
            if filt and filt not in hay:
                continue
            name = f"{c['nachname']}, {c['vorname']}".strip(", ")
            self.tree.insert("", "end", iid=c["id"],
                             values=(name, c["dienstgrad"], c["email"], c["ort"]))
        waehle = waehle or self.aktuell
        if waehle and self.tree.exists(waehle):
            self.tree.selection_set(waehle)
            self.tree.see(waehle)
        self.update_idletasks()
        self._ignoriere_auswahl = False
        n = len(self.store.contacts)
        self.lbl_anzahl.configure(text=f"{n} Kontakt{'e' if n != 1 else ''}")

    def _auswahl(self, _event=None):
        if self._ignoriere_auswahl:
            return
        sel = self.tree.selection()
        if not sel or sel[0] == self.aktuell:
            return
        if not self.verlassen():
            self._ignoriere_auswahl = True
            if self.aktuell and self.tree.exists(self.aktuell):
                self.tree.selection_set(self.aktuell)
            else:
                self.tree.selection_remove(*self.tree.selection())
            self.update_idletasks()
            self._ignoriere_auswahl = False
            return
        contact = self.store.contact_by_id(sel[0])
        if contact:
            self._lade_formular(contact)

    # ------------------------------------------------------------------ Formular
    def _baue_formular(self):
        rechts = ttk.LabelFrame(self, text="Kontakt bearbeiten", padding=14)
        rechts.grid(row=1, column=1, sticky="nsew")
        rechts.columnconfigure(1, weight=1)
        self.vars = {key: tk.StringVar() for key, _ in FELDER}
        self.eingaben = {}
        for r, (key, label) in enumerate(FELDER):
            ttk.Label(rechts, text=label).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            if key == "anrede":
                w = ttk.Combobox(rechts, textvariable=self.vars[key], values=ANREDEN, state="readonly",
                                 width=14)
                w.grid(row=r, column=1, sticky="w", pady=4)
            elif key == "dienstgrad":
                w = ttk.Combobox(rechts, textvariable=self.vars[key], values=DIENSTGRADE, width=14)
                w.grid(row=r, column=1, sticky="w", pady=4)
            elif key == "plz":
                w = ttk.Entry(rechts, textvariable=self.vars[key], width=8)
                w.grid(row=r, column=1, sticky="w", pady=4)
            else:
                w = ttk.Entry(rechts, textvariable=self.vars[key])
                w.grid(row=r, column=1, sticky="ew", pady=4)
            self.eingaben[key] = w
        self.lbl_meldung = ttk.Label(rechts, text="", wraplength=320)
        self.lbl_meldung.grid(row=len(FELDER), column=0, columnspan=2, sticky="w", pady=(10, 0))
        knoepfe = ttk.Frame(rechts)
        knoepfe.grid(row=len(FELDER) + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(knoepfe, text="Speichern", style="Primar.TButton",
                   command=self._speichern).pack(side="right")
        ttk.Button(knoepfe, text="Verwerfen", command=self._verwerfen).pack(side="right", padx=6)
        ttk.Label(rechts, text="Der Dienstgrad kann frei eingegeben werden. In der Vorlage steht "
                  "er als Platzhalter {Dienstgrad} zur Verfügung.", style="Hinweis.TLabel",
                  wraplength=320).grid(row=len(FELDER) + 2, column=0, columnspan=2, sticky="w",
                                       pady=(16, 0))
        for key in self.vars:
            self.eingaben[key].bind("<Return>", lambda _e: self._speichern())

    def _formular_werte(self) -> dict:
        werte = {k: v.get().strip() for k, v in self.vars.items()}
        if werte["anrede"] == "keine Angabe":
            werte["anrede"] = ""
        return werte

    def _setze_formular(self, werte: dict):
        for key, var in self.vars.items():
            val = werte.get(key, "")
            if key == "anrede" and not val:
                val = "keine Angabe"
            var.set(val)
        self._original = self._formular_werte()
        self.lbl_meldung.configure(text="")

    def _leeres_formular(self):
        self.aktuell = None
        self._setze_formular({"anrede": "Herr"})

    def _lade_formular(self, contact: dict):
        self.aktuell = contact["id"]
        self._setze_formular(contact)

    def ist_geaendert(self) -> bool:
        return self._formular_werte() != self._original

    def verlassen(self) -> bool:
        """Vor dem Verlassen ungespeicherte Änderungen klären. False = bleiben."""
        if not self.ist_geaendert():
            return True
        werte = self._formular_werte()
        if not self.aktuell and not any(v for k, v in werte.items() if k != "anrede"):
            return True
        antwort = messagebox.askyesnocancel("Ungespeicherte Änderungen",
                                            "Änderungen am Kontakt speichern?", parent=self)
        if antwort is None:
            return False
        if antwort:
            return self._speichern()
        self._verwerfen()
        return True

    def _speichern(self) -> bool:
        werte = self._formular_werte()
        if not werte["vorname"] and not werte["nachname"]:
            self.lbl_meldung.configure(text="Bitte mindestens Vor- oder Nachnamen eingeben.",
                                       style="Fehler.TLabel")
            return False
        if werte["email"] and not EMAIL_RE.match(werte["email"]):
            self.lbl_meldung.configure(text="Die E-Mail-Adresse sieht nicht gültig aus.",
                                       style="Fehler.TLabel")
            self.eingaben["email"].focus_set()
            return False
        if self.aktuell:
            werte["id"] = self.aktuell
        gespeichert = self.store.upsert_contact(werte)
        self.aktuell = gespeichert["id"]
        self._original = self._formular_werte()
        self.lade_liste(waehle=self.aktuell)
        self.lbl_meldung.configure(text=f"Gespeichert: {werte['vorname']} {werte['nachname']}",
                                   style="Ok.TLabel")
        self.app.kontakte_geaendert()
        return True

    def _verwerfen(self):
        contact = self.store.contact_by_id(self.aktuell) if self.aktuell else None
        if contact:
            self._lade_formular(contact)
        else:
            self._leeres_formular()

    def _neu(self):
        if not self.verlassen():
            return
        self._ignoriere_auswahl = True
        self.tree.selection_remove(*self.tree.selection())
        self.update_idletasks()
        self._ignoriere_auswahl = False
        self._leeres_formular()
        self.eingaben["vorname"].focus_set()

    def _loeschen(self):
        if not self.aktuell:
            return
        c = self.store.contact_by_id(self.aktuell)
        if not c or not messagebox.askyesno(
                "Kontakt löschen", f"{c['vorname']} {c['nachname']} wirklich löschen?", parent=self):
            return
        self.store.delete_contact(self.aktuell)
        self._leeres_formular()
        self.lade_liste()
        self.app.kontakte_geaendert()

    # ------------------------------------------------------------------ Import/Export
    def _import(self):
        if not self.verlassen():
            return
        path = filedialog.askopenfilename(
            parent=self, title="Kontaktliste importieren",
            filetypes=[("Tabellen", "*.xlsx *.xlsm *.csv *.txt"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            headers, rows = lese_tabelle(Path(path))
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Import nicht möglich", str(err), parent=self)
            return
        ImportDialog(self, headers, rows, Path(path).name)

    def _export(self):
        if not self.store.contacts:
            messagebox.showinfo("Export", "Es sind noch keine Kontakte vorhanden.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Kontakte exportieren",
                                            defaultextension=".csv", initialfile="Kontakte.csv",
                                            filetypes=[("CSV-Datei", "*.csv")])
        if path:
            exportiere_csv(self.store.contacts, Path(path))
            messagebox.showinfo("Export", f"{len(self.store.contacts)} Kontakte gespeichert.", parent=self)

    def nach_import(self, added: int, skipped: int):
        self.lade_liste()
        self.app.kontakte_geaendert()
        text = f"{added} Kontakt{'e' if added != 1 else ''} importiert."
        if skipped:
            text += f"\n{skipped} übersprungen (bereits vorhanden: gleicher Name oder gleiche E-Mail)."
        messagebox.showinfo("Import abgeschlossen", text, parent=self)


class ImportDialog(tk.Toplevel):
    NICHT = "– nicht verwenden –"

    def __init__(self, tab: KontakteTab, headers: list[str], rows: list[list[str]], dateiname: str):
        super().__init__(tab)
        self.tab = tab
        self.headers, self.rows = headers, rows
        self.title("Kontakte importieren")
        self.transient(tab.winfo_toplevel())
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=f"{dateiname}: {len(rows)} Zeilen gefunden", style="Titel.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(frame, text="Bitte prüfen, welche Spalte zu welchem Feld gehört:",
                  style="Hinweis.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 10))
        auto = auto_zuordnung(headers)
        self.combos = {}
        werte = [self.NICHT] + headers
        half = (len(ZIELFELDER) + 1) // 2
        for i, (key, label) in enumerate(ZIELFELDER):
            r, c = (i % half) + 2, (i // half) * 2
            ttk.Label(frame, text=label).grid(row=r, column=c, sticky="w", padx=(0 if c == 0 else 18, 8), pady=3)
            cb = ttk.Combobox(frame, values=werte, state="readonly", width=26)
            cb.set(headers[auto[key]] if auto[key] is not None else self.NICHT)
            cb.grid(row=r, column=c + 1, sticky="w", pady=3)
            cb.bind("<<ComboboxSelected>>", lambda _e: self._vorschau())
            self.combos[key] = cb
        row = half + 2
        ttk.Label(frame, text="Vorschau (erste Einträge)", style="Fett.TLabel").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(14, 4))
        self.tree = ttk.Treeview(frame, columns=("anrede", "dg", "name", "adresse", "mail"),
                                 show="headings", height=6)
        for col, text, width in (("anrede", "Anrede", 60), ("dg", "Dienstgrad", 80), ("name", "Name", 180),
                                 ("adresse", "Anschrift", 240), ("mail", "E-Mail", 200)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w")
        self.tree.grid(row=row + 1, column=0, columnspan=4, sticky="nsew")
        self.lbl_anzahl = ttk.Label(frame, text="", style="Hinweis.TLabel")
        self.lbl_anzahl.grid(row=row + 2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        knoepfe = ttk.Frame(frame)
        knoepfe.grid(row=row + 3, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Button(knoepfe, text="Importieren", style="Primar.TButton", command=self._import).pack(side="right")
        ttk.Button(knoepfe, text="Abbrechen", command=self.destroy).pack(side="right", padx=6)
        self._vorschau()
        center_on(self, tab.winfo_toplevel())
        self.grab_set()

    def _mapping(self) -> dict:
        out = {}
        for key, cb in self.combos.items():
            val = cb.get()
            out[key] = self.headers.index(val) if val in self.headers else None
        return out

    def _vorschau(self):
        kontakte = wende_an(self.headers, self.rows, self._mapping())
        self.tree.delete(*self.tree.get_children())
        for c in kontakte[:8]:
            adresse = ", ".join(p for p in (c["strasse"], f"{c['plz']} {c['ort']}".strip()) if p)
            self.tree.insert("", "end", values=(c["anrede"], c["dienstgrad"],
                                                f"{c['vorname']} {c['nachname']}", adresse, c["email"]))
        ohne_mail = sum(1 for c in kontakte if not c["email"])
        text = f"{len(kontakte)} Kontakte werden übernommen."
        if ohne_mail:
            text += f" {ohne_mail} davon ohne E-Mail-Adresse."
        self.lbl_anzahl.configure(text=text)

    def _import(self):
        kontakte = wende_an(self.headers, self.rows, self._mapping())
        if not kontakte:
            messagebox.showwarning("Nichts zu importieren",
                                   "Es wurden keine Namen gefunden. Bitte die Zuordnung prüfen.", parent=self)
            return
        added, skipped = self.tab.store.add_contacts(kontakte)
        self.grab_release()
        self.destroy()
        self.tab.nach_import(added, skipped)
