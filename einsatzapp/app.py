"""Hauptfenster mit den Bereichen Einsatz, Gespeicherte Einsätze, Kontakte, Vorlage, Einstellungen."""

import os
import sys
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import messagebox, ttk

from . import APP_NAME, __version__
from .einsaetze_ui import EinsaetzeTab
from .einsatz_ui import EinsatzTab
from .einstellungen_ui import EinstellungenTab
from .kontakte_ui import KontakteTab
from .paths import resource_dir
from .storage import Store
from .vorlage_ui import VorlageTab
from .widgets import install_klickfokus, install_mousewheel, setup_styles


def _dpi_bewusst():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


class App(tk.Tk):
    def __init__(self):
        _dpi_bewusst()
        super().__init__(className=APP_NAME)
        self.title(APP_NAME)
        self.store = Store()
        self.store.ersteinrichtung()
        setup_styles(self)
        self._icon()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.einsatz = EinsatzTab(self.nb, self)
        self.verlauf = EinsaetzeTab(self.nb, self)
        self.kontakte = KontakteTab(self.nb, self)
        self.vorlage = VorlageTab(self.nb, self)
        self.einstellungen = EinstellungenTab(self.nb, self)
        self.nb.add(self.einsatz, text="  Einsatz  ")
        self.nb.add(self.verlauf, text="  Gespeicherte Einsätze  ")
        self.nb.add(self.kontakte, text="  Kontakte  ")
        self.nb.add(self.vorlage, text="  Vorlage  ")
        self.nb.add(self.einstellungen, text="  Einstellungen  ")
        self._aktiv = self.einsatz
        self.nb.bind("<<NotebookTabChanged>>", self._tab_gewechselt)
        self.protocol("WM_DELETE_WINDOW", self._schliessen)
        install_mousewheel(self)
        install_klickfokus(self)
        self._fenstergroesse()

    def _icon(self):
        try:
            self._icon_img = tk.PhotoImage(file=str(resource_dir() / "icon.png"))
            self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    def _fenstergroesse(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1180, sw - 80), min(820, sh - 120)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(20, (sh - h) // 3)}")
        self.minsize(min(940, w), min(620, h))

    def _tab_gewechselt(self, _event=None):
        neu = self.nametowidget(self.nb.select())
        alt = self._aktiv
        if neu is alt:
            return
        if hasattr(alt, "verlassen") and not alt.verlassen():
            self.nb.select(alt)
            return
        self._aktiv = neu

    def kontakte_geaendert(self):
        self.einsatz.aktualisiere_liste()

    def einsaetze_geaendert(self):
        self.einsatz._pruefe_gespeichert()
        self.verlauf.aktualisiere()

    def zeige_verlauf(self, eid: str | None = None):
        self.nb.select(self.verlauf)
        if eid:
            self.verlauf.zeige(eid)

    def einsatz_ergaenzen(self, rec: dict):
        self.nb.select(self.einsatz)
        if self.nametowidget(self.nb.select()) is self.einsatz:
            self.einsatz.lade_einsatz(rec)

    def _schliessen(self):
        for tab in (self.kontakte, self.vorlage):
            if not tab.verlassen():
                self.nb.select(tab)
                return
        if getattr(self.einsatz, "_laeuft", False) and not messagebox.askyesno(
                "Noch beschäftigt", "Es werden gerade E-Mail-Entwürfe erstellt. Trotzdem beenden?",
                parent=self):
            return
        self.destroy()

    def report_callback_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            log = self.store.dir / "fehler.log"
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} · Version {__version__}\n{text}\n")
        except OSError:
            log = None
        messagebox.showerror("Unerwarteter Fehler",
                             f"{val}\n\nDetails stehen in: {log}" if log else text, parent=self)


def _selbsttest(ziel: str) -> int:
    """Prüft das fertige Paket ohne Oberfläche: Schriften, Beispielvorlage, PDF + Sammel-PDF."""
    import tempfile
    from pathlib import Path

    from pypdf import PdfReader

    from .generator import fuege_zusammen
    from .pdfgen import Renderer
    from .placeholders import demo_context

    tmp = Path(tempfile.mkdtemp(prefix="eb_selbsttest_"))
    store = Store(tmp)
    store.ersteinrichtung()
    if not store.image_path(store.template["unterschrift"]["datei"]):
        return 2
    ctx, gender = demo_context()
    einzel = tmp / "einzel.pdf"
    r = Renderer(store.template, store.assets, use_system_fonts=False)
    r.add_page(ctx, gender)
    r.save(einzel, title="Selbsttest")
    fuege_zusammen([einzel, einzel], Path(ziel))
    return 0 if len(PdfReader(ziel).pages) == 2 else 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--selbsttest":
        sys.exit(_selbsttest(sys.argv[2]))
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
