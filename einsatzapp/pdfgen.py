"""PDF-Erzeugung im Layout der Original-Bescheinigung (A4, Maße in Punkt)."""

import logging
import os
import sys
from pathlib import Path

from fpdf import FPDF

from . import APP_NAME, __version__
from .paths import resource_dir
from .placeholders import render

logging.getLogger("fpdf").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)

MM = 72 / 25.4  # Punkt pro Millimeter

# Layout, vermessen am Original (Arial Narrow 11 pt, Zeilenabstand 14,4 pt)
LEFT = 71.1
TEXT_WIDTH = 484.0
LINE = 14.4
BODY_SIZE = 11
KOPF_X, KOPF_BASE, KOPF_SIZE = 433.8, 118.9, 11
ADDR_BASE = 188.5
INFO_LABEL_RIGHT, INFO_VALUE_X, INFO_BASE = 417.3, 436.8, 176.1
INFO_SIZE, INFO_PITCH, INFO_WRAP_PITCH, INFO_VALUE_WIDTH = 9, 15.0, 10.5, 140.0
DATE_LABEL_RIGHT, DATE_VALUE_X, DATE_BASE, DATE_SIZE = 447.4, 467.0, 342.7, 10
TITLE_BASE, TITLE_SIZE = 358.2, 14
SALUTATION_BASE = 402.8

SCHRIFTEN = ["Arial Narrow", "Arial"]

_SYSTEM_FONTS = {
    # (regulär, fett) – Dateinamen je Plattform
    "Arial Narrow": {
        "darwin": ("Arial Narrow.ttf", "Arial Narrow Bold.ttf"),
        "nt": ("ARIALN.TTF", "ARIALNB.TTF"),
    },
    "Arial": {
        "darwin": ("Arial.ttf", "Arial Bold.ttf"),
        "nt": ("arial.ttf", "arialbd.ttf"),
    },
}
_BUNDLED = {
    "Arial Narrow": ("LiberationSansNarrow-Regular.ttf", "LiberationSansNarrow-Bold.ttf"),
    "Arial": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
}


def _font_dirs() -> list[Path]:
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts"]
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        return [windir / "Fonts", local]
    return []


def resolve_fonts(family: str, use_system: bool = True) -> tuple[str, str, str]:
    """Liefert Pfade (regulär, fett, Kopfzeile fett). Systemschrift wenn vorhanden,
    sonst die metrisch identische Liberation-Schrift aus dem App-Paket."""
    family = family if family in _BUNDLED else "Arial Narrow"

    def find(fam):
        key = "darwin" if sys.platform == "darwin" else ("nt" if os.name == "nt" else None)
        names = _SYSTEM_FONTS[fam].get(key) if (use_system and key) else None
        if names:
            for directory in _font_dirs():
                reg, bold = directory / names[0], directory / names[1]
                if reg.is_file() and bold.is_file():
                    return str(reg), str(bold)
        fonts = resource_dir() / "fonts"
        return str(fonts / _BUNDLED[fam][0]), str(fonts / _BUNDLED[fam][1])

    regular, bold = find(family)
    _, kopf_bold = find("Arial")
    return regular, bold, kopf_bold


class Renderer:
    """Erzeugt eine oder mehrere Bescheinigungsseiten in ein PDF."""

    def __init__(self, template: dict, assets_dir: Path, use_system_fonts: bool = True):
        self.tpl = template
        self.assets = Path(assets_dir)
        self.pdf = FPDF(unit="pt", format="A4")
        self.pdf.set_auto_page_break(False)
        self.pdf.set_margins(0, 0, 0)
        self.pdf.c_margin = 0
        regular, bold, kopf = resolve_fonts(template.get("schrift"), use_system_fonts)
        self.pdf.add_font("Body", "", regular)
        self.pdf.add_font("Body", "B", bold)
        self.pdf.add_font("Kopf", "B", kopf)
        self.pdf.set_creator(f"{APP_NAME} {__version__}")
        self.pdf.set_lang("de")
        self.unknown: set = set()

    # ------------------------------------------------------------------ Helfer
    def _r(self, text, ctx, gender):
        return render(text, ctx, gender, self.unknown)

    def _wrap(self, text: str, width: float) -> list[str]:
        words = text.split(" ")
        lines, current = [], ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if not current or self.pdf.get_string_width(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _image(self, spec: dict, y_pt: float | None = None):
        name = (spec or {}).get("datei")
        if not name:
            return
        path = self.assets / name
        if not path.is_file():
            return
        x = float(spec.get("x") or 0) * MM
        y = y_pt if y_pt is not None else float(spec.get("y") or 0) * MM
        w = float(spec.get("b") or 0) * MM
        h = float(spec.get("h") or 0) * MM
        self.pdf.image(str(path), x=x, y=y, w=w, h=h)

    # ------------------------------------------------------------------ Seite
    def add_page(self, ctx: dict, gender: int):
        pdf, tpl = self.pdf, self.tpl
        pdf.add_page()

        # Briefkopf
        self._image(tpl.get("logo_links"))
        self._image(tpl.get("logo_rechts"))
        kopf = self._r(tpl.get("kopf_text", ""), ctx, gender).strip()
        if kopf:
            pdf.set_font("Kopf", "B", KOPF_SIZE)
            for i, line in enumerate(kopf.split("\n")):
                pdf.text(KOPF_X, KOPF_BASE + i * 13.2, line)

        # Anschrift (leere Zeilen entfallen, z. B. ohne Straße)
        pdf.set_font("Body", "", BODY_SIZE)
        addr = [l for l in self._r(tpl.get("anschrift", ""), ctx, gender).split("\n") if l.strip()]
        for i, line in enumerate(addr):
            pdf.text(LEFT, ADDR_BASE + i * LINE, line)

        # Infoblock rechts: „Bezeichnung | Wert“
        pdf.set_font("Body", "", INFO_SIZE)
        y = INFO_BASE
        for raw in (tpl.get("infoblock") or "").split("\n"):
            if not raw.strip():
                y += INFO_PITCH
                continue
            label, value = raw.split("|", 1) if "|" in raw else ("", raw)
            label = self._r(label, ctx, gender).strip()
            value = self._r(value, ctx, gender).strip()
            if label:
                pdf.text(INFO_LABEL_RIGHT - pdf.get_string_width(label), y, label)
            lines = self._wrap(value, INFO_VALUE_WIDTH) if value else [""]
            for j, line in enumerate(lines):
                pdf.text(INFO_VALUE_X, y + j * INFO_WRAP_PITCH, line)
            y += INFO_PITCH + (len(lines) - 1) * INFO_WRAP_PITCH

        # Datum
        pdf.set_font("Body", "", DATE_SIZE)
        label = self._r(tpl.get("datum_bezeichnung", ""), ctx, gender).strip()
        value = self._r(tpl.get("datum_wert", ""), ctx, gender).strip()
        if label:
            pdf.text(DATE_LABEL_RIGHT - pdf.get_string_width(label), DATE_BASE, label)
        if value:
            pdf.text(DATE_VALUE_X, DATE_BASE, value)

        # Titel
        pdf.set_font("Body", "B", TITLE_SIZE)
        y = TITLE_BASE
        title = self._r(tpl.get("titel", ""), ctx, gender).strip()
        title_lines = [l for part in title.split("\n") for l in self._wrap(part, TEXT_WIDTH)] if title else []
        for i, line in enumerate(title_lines):
            pdf.text(LEFT, TITLE_BASE + i * 16.8, line)
        if title_lines:
            y = TITLE_BASE + (len(title_lines) - 1) * 16.8

        # Anrede und Text
        pdf.set_font("Body", "", BODY_SIZE)
        y = max(SALUTATION_BASE, y + 44.6)
        salutation = self._r(tpl.get("anrede", ""), ctx, gender).strip()
        if salutation:
            pdf.text(LEFT, y, salutation)
            y += 2 * LINE
        body = self._r(tpl.get("text", ""), ctx, gender).strip("\n")
        for paragraph in body.split("\n"):
            if not paragraph.strip():
                y += LINE
                continue
            for line in self._wrap(paragraph.strip(), TEXT_WIDTH):
                pdf.text(LEFT, y, line)
                y += LINE
        y += LINE  # Leerzeile vor der Grußformel

        # Grußformel, Unterschrift, Unterzeichner
        for line in self._r(tpl.get("gruss", ""), ctx, gender).strip("\n").split("\n"):
            if line.strip():
                pdf.text(LEFT, y, line.strip())
            y += LINE
        last_closing = y - LINE
        sig = tpl.get("unterschrift") or {}
        self._image(sig, y_pt=last_closing + 0.5 + float(sig.get("dy") or 0) * MM)
        y = last_closing + 4 * LINE
        for line in self._r(tpl.get("unterzeichner", ""), ctx, gender).strip("\n").split("\n"):
            if line.strip():
                pdf.text(LEFT, y, line.strip())
            y += LINE

    def save(self, path: Path, title: str = ""):
        if title:
            self.pdf.set_title(title)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(path))
