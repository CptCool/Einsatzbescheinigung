"""Lizenzhinweise: MIT-Lizenz der App und Lizenzen der mitgelieferten Komponenten.

Beim Bauen (siehe einsatzbescheinigung.spec) entsteht daraus LIZENZEN.txt im Programmpaket.
Die App zeigt den Text unter Einstellungen › Lizenzen an.
"""

import sys
from importlib import metadata
from pathlib import Path

from . import APP_NAME, __version__
from .paths import resource_dir

DATEI = "LIZENZEN.txt"
QUELLTEXT = "https://github.com/CptCool/Einsatzbescheinigung"
EIGENE_LIZENZ = Path(__file__).resolve().parent.parent / "LICENSE"
TEXTE = Path(__file__).resolve().parent / "lizenztexte"

# Python-Pakete im Programmpaket (requirements.txt samt Abhängigkeiten): Name, Lizenz, Quelle
PAKETE = [
    ("fpdf2", "LGPL-3.0-only", "https://github.com/py-pdf/fpdf2"),
    ("fonttools", "MIT", "https://github.com/fonttools/fonttools"),
    ("pillow", "MIT-CMU", "https://github.com/python-pillow/Pillow"),
    ("pypdf", "BSD-3-Clause", "https://github.com/py-pdf/pypdf"),
    ("openpyxl", "MIT", "https://foss.heptapod.net/openpyxl/openpyxl"),
    ("et_xmlfile", "MIT", "https://foss.heptapod.net/openpyxl/et_xmlfile"),
]

# Mitgelieferte Schriften: Name, Lizenz, Lizenzdateien in einsatzapp/fonts
SCHRIFTEN = [
    ("Liberation Sans 2.1.5", "SIL OFL 1.1", ["LiberationSans-LICENSE.txt"]),
    ("Liberation Sans Narrow 1.07.4", "GPL-2.0 mit Font-Ausnahme",
     ["LiberationSansNarrow-LICENSE.txt", "LiberationSansNarrow-COPYING.txt"]),
]

LIZENZDATEI_PRAEFIXE = ("LICEN", "COPYING", "NOTICE")


def _abschnitt(titel: str, inhalt: str) -> str:
    linie = "=" * 78
    return f"{linie}\n{titel}\n{linie}\n\n{inhalt.strip()}\n\n"


def paket_lizenztexte(name: str) -> list[tuple[str, str]]:
    """Lizenzdateien aus den Metadaten eines installierten Pakets: [(Dateiname, Text)]."""
    dist = metadata.distribution(name)
    texte = []
    for datei in sorted(dist.files or [], key=str):
        teile = datei.parts
        if not any(t.endswith(".dist-info") for t in teile[:-1]):
            continue
        if datei.name.upper().startswith(LIZENZDATEI_PRAEFIXE):
            texte.append((datei.name, Path(dist.locate_file(datei)).read_text(encoding="utf-8")))
    if not texte:
        raise FileNotFoundError(f"Keine Lizenzdatei für {name} gefunden")
    return texte


def _python_lizenz() -> str:
    basis = Path(sys.base_prefix)
    kandidaten = [basis / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt",
                  basis / "LICENSE.txt", basis / "Lib" / "LICENSE.txt"]
    for pfad in kandidaten:
        if pfad.is_file():
            return pfad.read_text(encoding="utf-8")
    return "PSF License Agreement for Python: https://docs.python.org/3/license.html"


def _tk_version() -> str:
    try:
        import tkinter

        return tkinter.Tcl().eval("info patchlevel")
    except Exception:  # noqa: BLE001 – nur für die Anzeige
        return ""


def erzeuge_text() -> str:
    """Kompletter Lizenztext aus dem Quelltext-Stand (beim Bauen bzw. ohne Programmpaket)."""
    python = sys.version.split()[0]
    tk = _tk_version()
    zeilen = [(name, metadata.version(name), lizenz) for name, lizenz, _ in PAKETE]
    zeilen += [(name.rsplit(" ", 1)[0], name.rsplit(" ", 1)[1], lizenz) for name, lizenz, _ in SCHRIFTEN]
    zeilen += [("Python", python, "PSF-2.0"), ("Tcl/Tk", tk, "Tcl/Tk-Lizenz (BSD-artig)"),
               ("PyInstaller-Bootloader", "", "GPL-2.0 mit Ausnahme für damit gebaute Programme")]
    tabelle = "\n".join(f"  {n:<24} {v:<10} {lz}" for n, v, lz in zeilen)

    kopf = (
        f"{APP_NAME} {__version__}\n"
        f"Quelltext: {QUELLTEXT}\n\n"
        f"{APP_NAME} ist freie Software unter der MIT-Lizenz (Abschnitt 1). Die fertigen Programme\n"
        "enthalten außerdem Komponenten anderer Autoren, die unter deren eigenen Lizenzen stehen:\n\n"
        f"  {'Komponente':<24} {'Version':<10} Lizenz\n{tabelle}\n\n"
        "Hinweis zu fpdf2 (LGPL-3.0): fpdf2 wird unverändert verwendet. Da der vollständige\n"
        "Quelltext dieser App öffentlich ist, lässt sich fpdf2 gegen eine andere oder geänderte\n"
        "Version austauschen, indem man die App aus dem Quelltext startet oder neu baut (README).\n"
        "Quelltext von fpdf2: https://github.com/py-pdf/fpdf2\n\n"
    )
    teile = [kopf, _abschnitt(f"1. {APP_NAME} – MIT License", EIGENE_LIZENZ.read_text(encoding="utf-8"))]
    nr = 2
    for name, lizenz, quelle in PAKETE:
        inhalt = f"Quelle: {quelle}\n\n" + "\n\n".join(
            (f"--- {datei} ---\n\n{text.strip()}" if len(texte) > 1 else text)
            for texte in [paket_lizenztexte(name)] for datei, text in texte)
        teile.append(_abschnitt(f"{nr}. {name} {metadata.version(name)} – {lizenz}", inhalt))
        nr += 1
    for name, lizenz, dateien in SCHRIFTEN:
        inhalt = "\n\n".join((resource_dir() / "fonts" / d).read_text(encoding="utf-8").strip()
                             for d in dateien)
        teile.append(_abschnitt(f"{nr}. Schrift {name} – {lizenz}", inhalt))
        nr += 1
    teile.append(_abschnitt(f"{nr}. Python {python} – PSF-2.0", _python_lizenz()))
    nr += 1
    teile.append(_abschnitt(f"{nr}. Tcl/Tk {tk} – Tcl/Tk-Lizenz",
                            (TEXTE / "Tcl-Tk.txt").read_text(encoding="utf-8")))
    nr += 1
    teile.append(_abschnitt(f"{nr}. GNU General Public License 3.0 (Grundlage der LGPL-3.0 von fpdf2)",
                            (TEXTE / "GPL-3.0.txt").read_text(encoding="utf-8")))
    return "".join(teile)


def text() -> str:
    """Lizenztext für die Anzeige in der App."""
    datei = resource_dir() / DATEI
    if datei.is_file():
        return datei.read_text(encoding="utf-8")
    if not getattr(sys, "frozen", False):
        try:
            return erzeuge_text()
        except (OSError, metadata.PackageNotFoundError):
            pass
    return f"{APP_NAME} {__version__} – MIT-Lizenz.\nAlle Lizenztexte: {QUELLTEXT}\n"
