"""Bereich „Einstellungen“: Mailprogramm, BCC, Ablageordner, Test-Entwurf, Lizenzen."""

import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .generator import vorschau
from .kontakte_ui import EMAIL_RE
from .lizenzinfo import QUELLTEXT
from .lizenzinfo import text as lizenztext
from .mailer import PROGRAMME, Entwurf, Mailer, ermittle_auto, verfuegbare_programme
from .paths import open_path
from .widgets import center_on

HINWEISE = {
    "applemail": "Die Entwürfe öffnen sich als Fenster in Apple Mail. Beim ersten Mal fragt macOS, "
                 "ob die App Mail steuern darf – bitte erlauben.",
    "outlook_mac": "Funktioniert mit dem klassischen Outlook für Mac. Beim „neuen Outlook“ bitte "
                   "„Legacy Outlook“ aktivieren oder Apple Mail verwenden.",
    "outlook_win": "Funktioniert mit dem klassischen Outlook (Office). Das „neue Outlook“ lässt sich "
                   "nicht fernsteuern – dann bitte „.eml-Dateien“ wählen.",
    "mapi": "Nutzt das in Windows eingestellte Standard-Mailprogramm (z. B. Outlook klassisch, "
            "Thunderbird, eM Client).",
    "thunderbird": "Die Entwürfe öffnen sich als Verfassen-Fenster in Thunderbird.",
    "xdg": "Nutzt das Standard-Mailprogramm der Desktop-Umgebung (Thunderbird, Evolution, KMail …).",
    "eml": "Für jede Mail wird eine .eml-Datei im Einsatzordner angelegt und geöffnet. Outlook öffnet "
           "sie als bearbeitbaren Entwurf; Apple Mail nur zur Ansicht (dort „Erneut senden“ wählen).",
}


class EinstellungenTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=14)
        self.app = app
        self.store = app.store
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Einstellungen", style="Titel.TLabel").grid(row=0, column=0, sticky="w",
                                                                          pady=(0, 10))
        s = self.store.settings
        self._keys = verfuegbare_programme()
        self._labels = [PROGRAMME[k] for k in self._keys]

        mail = ttk.LabelFrame(self, text="E-Mail", padding=12)
        mail.grid(row=1, column=0, sticky="ew")
        mail.columnconfigure(1, weight=1)
        ttk.Label(mail, text="Mailprogramm").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_prog = tk.StringVar(value=PROGRAMME.get(s.get("mailprogramm"), PROGRAMME["auto"]))
        cb = ttk.Combobox(mail, textvariable=self.v_prog, values=self._labels, state="readonly", width=44)
        cb.grid(row=0, column=1, sticky="w", pady=4)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._speichern())
        self.lbl_prog = ttk.Label(mail, text="", style="Hinweis.TLabel", wraplength=640)
        self.lbl_prog.grid(row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(mail, text="Kopie (BCC) an").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_bcc = tk.StringVar(value=s.get("bcc", ""))
        ttk.Entry(mail, textvariable=self.v_bcc, width=46).grid(row=2, column=1, sticky="w", pady=4)
        self.lbl_bcc = ttk.Label(mail, text="", style="Hinweis.TLabel")
        self.lbl_bcc.grid(row=3, column=1, sticky="w")
        self.v_bcc.trace_add("write", lambda *_: self._speichern())

        self.v_mails = tk.BooleanVar(value=bool(s.get("mails_erstellen", True)))
        ttk.Checkbutton(mail, text="E-Mail-Entwürfe standardmäßig erstellen", variable=self.v_mails,
                        command=self._speichern).grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Button(mail, text="Test-Entwurf erstellen …", command=self._test).grid(
            row=5, column=1, sticky="w", pady=(10, 0))

        ablage = ttk.LabelFrame(self, text="Ablage", padding=12)
        ablage.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ablage.columnconfigure(1, weight=1)
        ttk.Label(ablage, text="PDF-Ordner").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.v_ordner = tk.StringVar(value=str(self.store.output_dir()))
        ttk.Entry(ablage, textvariable=self.v_ordner, state="readonly").grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(ablage, text="Ändern …", command=self._ordner_waehlen).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(ablage, text="Öffnen", command=self._ordner_oeffnen).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(ablage, text="Je Einsatz wird ein Unterordner angelegt, z. B. "
                  "„2026-04-07_1159_Einsatz_2026-117“.", style="Hinweis.TLabel").grid(
            row=1, column=1, columnspan=3, sticky="w")
        self.v_sammel = tk.BooleanVar(value=bool(s.get("sammel_pdf", True)))
        ttk.Checkbutton(ablage, text="Sammel-PDF (alle Bescheinigungen eines Einsatzes) standardmäßig erstellen",
                        variable=self.v_sammel, command=self._speichern).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(8, 0))

        daten = ttk.LabelFrame(self, text="Daten dieser App", padding=12)
        daten.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(daten, text=f"Kontakte, Vorlage und Einstellungen liegen in:\n{self.store.dir}",
                  style="Hinweis.TLabel").pack(side="left")
        ttk.Button(daten, text="Datenordner öffnen", command=lambda: open_path(self.store.dir)).pack(side="right")

        info = ttk.Frame(self)
        info.grid(row=4, column=0, sticky="w", pady=(16, 0))
        ttk.Label(info, text=f"Einsatzbescheinigung {__version__} · freie Software unter der MIT-Lizenz",
                  style="Hinweis.TLabel").pack(side="left")
        ttk.Button(info, text="Lizenzen …", command=lambda: LizenzDialog(self)).pack(side="left",
                                                                                     padx=(10, 0))
        self._zeige_hinweise()

    def _prog_key(self) -> str:
        label = self.v_prog.get()
        return self._keys[self._labels.index(label)] if label in self._labels else "auto"

    def _zeige_hinweise(self):
        key = self._prog_key()
        effektiv = ermittle_auto() if key == "auto" else key
        text = HINWEISE.get(effektiv, "")
        if key == "auto":
            text = f"Erkannt: {PROGRAMME[effektiv]}. " + text
        self.lbl_prog.configure(text=text)
        bcc = self.store.bcc_list()
        falsch = [a for a in bcc if not EMAIL_RE.match(a)]
        if falsch:
            self.lbl_bcc.configure(text="Ungültige Adresse: " + ", ".join(falsch), style="Fehler.TLabel")
        else:
            self.lbl_bcc.configure(text="Optional. Mehrere Adressen mit Komma trennen.", style="Hinweis.TLabel")

    def _speichern(self):
        s = self.store.settings
        s["mailprogramm"] = self._prog_key()
        s["bcc"] = self.v_bcc.get().strip()
        s["mails_erstellen"] = bool(self.v_mails.get())
        s["sammel_pdf"] = bool(self.v_sammel.get())
        self.store.save_settings()
        self._zeige_hinweise()

    def _ordner_waehlen(self):
        path = filedialog.askdirectory(parent=self, title="Ordner für die PDFs wählen",
                                       initialdir=str(self.store.output_dir().parent))
        if path:
            self.store.settings["ausgabeordner"] = path
            self.store.save_settings()
            self.v_ordner.set(path)

    def _ordner_oeffnen(self):
        ordner = self.store.output_dir()
        ordner.mkdir(parents=True, exist_ok=True)
        open_path(ordner)

    def _test(self):
        bcc = self.store.bcc_list()
        if any(not EMAIL_RE.match(a) for a in bcc):
            messagebox.showerror("BCC prüfen", "Bitte zuerst die BCC-Adresse korrigieren.", parent=self)
            return
        adresse = simpledialog.askstring("Test-Entwurf", "An welche Adresse soll der Test-Entwurf gehen?\n"
                                         "(Er wird nur geöffnet, nicht gesendet.)",
                                         initialvalue=bcc[0] if bcc else "", parent=self)
        if not adresse:
            return
        if not EMAIL_RE.match(adresse.strip()):
            messagebox.showerror("Test-Entwurf", "Die Adresse sieht nicht gültig aus.", parent=self)
            return
        try:
            pdf = vorschau(self.store.template, self.store.assets)
        except Exception as err:  # noqa: BLE001
            messagebox.showerror("Test-Entwurf", str(err), parent=self)
            return
        entwurf = Entwurf(adresse.strip(), "Test – Einsatzbescheinigung",
                          "Dies ist ein Test-Entwurf der App „Einsatzbescheinigung“.\n"
                          "Bitte nicht senden – einfach schließen.", [pdf], bcc)
        programm = self.store.settings.get("mailprogramm", "auto")
        self.configure(cursor="watch")

        def arbeit():
            try:
                info = Mailer(programm, pdf.parent).erstelle(entwurf)
                self.after(0, lambda: self._test_fertig(True, info))
            except Exception as err:  # noqa: BLE001
                self.after(0, lambda e=err: self._test_fertig(False, str(e)))

        threading.Thread(target=arbeit, daemon=True).start()

    def _test_fertig(self, ok: bool, info: str):
        self.configure(cursor="")
        if ok:
            messagebox.showinfo("Test-Entwurf", f"Erfolgreich: {info}.\nBitte den Entwurf im "
                                "Mailprogramm prüfen und anschließend verwerfen.", parent=self)
        else:
            messagebox.showerror("Test-Entwurf", info, parent=self)


class LizenzDialog(tk.Toplevel):
    """Zeigt die MIT-Lizenz der App und die Lizenzen der mitgelieferten Komponenten."""

    def __init__(self, parent):
        super().__init__(parent)
        top = parent.winfo_toplevel()
        self.title("Lizenzen")
        self.transient(top)
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.bind("<Escape>", lambda _e: self._schliessen())
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        txt = tk.Text(frame, width=100, height=32, wrap="none", font="TkFixedFont", relief="solid",
                      borderwidth=1, padx=8, pady=6)
        sy = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        sx = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        txt.insert("1.0", lizenztext())
        txt.configure(state="disabled")
        knoepfe = ttk.Frame(frame)
        knoepfe.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(knoepfe, text="Quelltext auf GitHub",
                   command=lambda: webbrowser.open(QUELLTEXT)).pack(side="left")
        ttk.Button(knoepfe, text="Schließen", command=self._schliessen).pack(side="right")
        center_on(self, top)
        self.focus_force()

    def _schliessen(self):
        top = self.master.winfo_toplevel()
        self.destroy()
        top.focus_force()
