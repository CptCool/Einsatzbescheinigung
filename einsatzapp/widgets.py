"""Gemeinsame Tk-Bausteine: Stile, scrollbarer Bereich, Mausrad, Hilfsdialoge."""

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FARBE_FEHLER = "#b00020"
FARBE_OK = "#1b7f2a"
FARBE_INFO = "#0a5fb4"
FARBE_HINWEIS = "#6b6b6b"


def setup_styles(root: tk.Tk):
    style = ttk.Style(root)
    if sys.platform.startswith("linux") and "clam" in style.theme_names():
        style.theme_use("clam")
    base = tkfont.nametofont("TkDefaultFont")
    size = base.cget("size")

    def grown(delta, weight="normal"):
        f = base.copy()
        f.configure(size=(size + delta) if size > 0 else (size - delta), weight=weight)
        return f

    root._fonts = {"titel": grown(4, "bold"), "fett": grown(0, "bold"), "klein": grown(-1)}
    style.configure("Titel.TLabel", font=root._fonts["titel"])
    style.configure("Fett.TLabel", font=root._fonts["fett"])
    style.configure("Hinweis.TLabel", foreground=FARBE_HINWEIS, font=root._fonts["klein"])
    style.configure("Fehler.TLabel", foreground=FARBE_FEHLER)
    style.configure("Ok.TLabel", foreground=FARBE_OK)
    style.configure("Info.TLabel", foreground=FARBE_INFO)
    style.configure("Primar.TButton", font=root._fonts["fett"], padding=(14, 6))
    style.configure("Treeview", rowheight=max(22, int(abs(size) * 1.9)))


def frame_background(widget) -> str:
    bg = ttk.Style(widget).lookup("TFrame", "background")
    return bg or widget.winfo_toplevel().cget("background")


class ScrollFrame(ttk.Frame):
    """Rahmen mit senkrechter Bildlaufleiste; Inhalte kommen in ``self.inner``."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=frame_background(self))
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._inner_changed)
        self.canvas.bind("<Configure>", self._canvas_changed)

    def _inner_changed(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_changed(self, event):
        self.canvas.itemconfigure(self._win, width=event.width)

    def scroll_units(self, units: int):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


_EIGENER_BILDLAUF = {"Text", "Treeview", "Listbox", "TCombobox"}


def install_mousewheel(root: tk.Tk):
    """Mausrad/Touchpad für alle ScrollFrames unter dem Mauszeiger."""

    def target(event):
        widget = root.winfo_containing(event.x_root, event.y_root)
        if widget is None:
            return None
        try:
            if widget.winfo_class() in _EIGENER_BILDLAUF:
                return None
        except tk.TclError:
            return None
        while widget is not None:
            if isinstance(widget, ScrollFrame):
                return widget
            widget = widget.master
        return None

    def on_wheel(event):
        sf = target(event)
        if sf is None:
            return
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            d = event.delta
            if abs(d) >= 120:
                units = -int(d / 120)
            else:
                units = -d
            if units == 0:
                units = -1 if d > 0 else 1
        sf.scroll_units(units)

    acc = {"dy": 0.0}

    def on_touchpad(event):  # Tk 9 (macOS Touchpad)
        sf = target(event)
        if sf is None:
            return
        try:
            _dx, dy = root.tk.splitlist(root.tk.call("tk::PreciseScrollDeltas", event.delta))
        except tk.TclError:
            return
        acc["dy"] += float(dy)
        steps = int(acc["dy"] / 8)
        if steps:
            acc["dy"] -= steps * 8
            sf.scroll_units(-steps)

    root.bind_all("<MouseWheel>", on_wheel, add="+")
    root.bind_all("<Button-4>", on_wheel, add="+")
    root.bind_all("<Button-5>", on_wheel, add="+")
    try:
        root.bind_all("<TouchpadScroll>", on_touchpad, add="+")
    except tk.TclError:
        pass


def install_klickfokus(root: tk.Tk):
    """macOS: Ein Klick in ein Eingabefeld macht dessen Fenster sicher zum aktiven Fenster.

    Nach dem Wechsel aus dem Mailprogramm oder nach dem Schließen eines Dialogs landet die
    Tastatur unter macOS sonst gelegentlich im zuvor aktiven Fenster – das angeklickte Feld zeigt
    zwar den Cursor, nimmt aber keine Eingabe an.
    """
    if sys.platform != "darwin":
        return

    def klick(event):
        try:
            event.widget.focus_force()
        except (tk.TclError, AttributeError):
            pass

    for klasse in ("TEntry", "TSpinbox", "Entry", "Text"):
        root.bind_class(klasse, "<ButtonPress-1>", klick, add="+")


def text_widget(master, height: int, width: int = 60) -> tk.Text:
    t = tk.Text(master, height=height, width=width, wrap="word", undo=True,
                font=tkfont.nametofont("TkDefaultFont"), relief="solid", borderwidth=1,
                padx=6, pady=4, highlightthickness=1)
    return t


def text_get(widget: tk.Text) -> str:
    return widget.get("1.0", "end-1c")


def text_set(widget: tk.Text, value: str):
    widget.delete("1.0", "end")
    widget.insert("1.0", value or "")
    widget.edit_reset()


def center_on(window: tk.Toplevel, parent: tk.Misc):
    window.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_rootx(), parent.winfo_rooty()
    w, h = window.winfo_reqwidth(), window.winfo_reqheight()
    window.geometry(f"+{max(0, px + (pw - w) // 2)}+{max(0, py + (ph - h) // 3)}")
