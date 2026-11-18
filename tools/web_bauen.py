"""Baut die Browser-Version als statische Website (z. B. für GitHub Pages).

    python tools/web_bauen.py [--ziel build/web] [--cache build/web-cache]

Lädt Pyodide (Python für den Browser) und die Python-Pakete in genau festgelegten Versionen,
prüft jede Datei anhand ihrer Prüfsumme und legt alles zusammen mit der App in den Zielordner.
Die fertige Website lädt zur Laufzeit nichts von fremden Servern nach.
Benötigt nur die Python-Standardbibliothek.
"""

import argparse
import base64
import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from einsatzapp import __version__  # noqa: E402

PYODIDE = "314.0.7"
PYODIDE_TGZ = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE}.tgz"
PYODIDE_SHA512 = "0YvXxEhfEdpLfb/XkM2BFAeMROq0iMUX2bzzH9pOttyMcWkwq+HbE5uyuGD82LN7y2q+SNvi/6V5JEsOlD2R1A=="
PYODIDE_CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE}/full/"
PYODIDE_DATEIEN = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip",
                   "pyodide-lock.json"]
# Für den Browser übersetzte Pakete aus der Pyodide-Distribution (Prüfsumme steht in pyodide-lock.json)
LOCK_PAKETE = ["pillow", "fonttools"]
# Reine Python-Pakete von PyPI – Versionen wie in requirements.txt
PYPI_WHEELS = {
    "fpdf2-2.9.0-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/2f/b0/f0e770163d0e635c81e8ba117686e31c6b172715e1185ff00ea2eb0b2f3d/fpdf2-2.9.0-py3-none-any.whl",  # noqa: E501
        "e57f9eb183a61bbfc1a16ccb3eb68654f9ef3de0d9a78e37015a0df2eb29ab89"),
    "pypdf-6.21.2-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/1b/4d/c9d2d67f204eff463237a1a8f5e25a6923b7b1043982b91fcaf104c8ef60/pypdf-6.21.2-py3-none-any.whl",  # noqa: E501
        "1d44d1a3a200f25062adff0085b02040e4646431ac2ccac22e42679e91466084"),
    "openpyxl-3.1.5-py2.py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl",  # noqa: E501
        "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2"),
    "et_xmlfile-2.0.0-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl",  # noqa: E501
        "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa"),
}
# Nur für die Desktop-Oberfläche (Tk) – im Browser nicht nötig
NUR_DESKTOP = {"app.py", "__main__.py", "widgets.py", "einsatz_ui.py", "einsaetze_ui.py",
               "kontakte_ui.py", "vorlage_ui.py", "einstellungen_ui.py"}
WEB_DATEIEN = ["index.html", "app.js", "worker.js", "style.css"]


def laden(url: str, cache: Path, name: str, pruefe) -> bytes:
    """Datei aus dem Cache oder aus dem Netz holen; ``pruefe(daten)`` muss True liefern."""
    pfad = cache / name
    if pfad.is_file() and pruefe(pfad.read_bytes()):
        return pfad.read_bytes()
    print(f"  lade {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "einsatzbescheinigung-build"})
    with urllib.request.urlopen(req, timeout=120) as antwort:
        daten = antwort.read()
    if not pruefe(daten):
        raise SystemExit(f"Prüfsumme falsch: {url}")
    cache.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return daten


def sha256(erwartet: str):
    return lambda d: hashlib.sha256(d).hexdigest() == erwartet


def sha512_b64(erwartet: str):
    return lambda d: base64.b64encode(hashlib.sha512(d).digest()).decode() == erwartet


def app_zip() -> bytes:
    """Python-Paket der App (ohne Tk-Oberfläche) samt Schriften, Beispielvorlage und Lizenz."""
    puffer = io.BytesIO()
    paket = ROOT / "einsatzapp"
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "LICENSE", "LICENSE")
        for datei in sorted(paket.rglob("*")):
            rel = datei.relative_to(paket)
            if (datei.is_dir() or "__pycache__" in rel.parts or datei.suffix == ".pyc"
                    or (len(rel.parts) == 1 and rel.name in NUR_DESKTOP)):
                continue
            z.write(datei, f"einsatzapp/{rel.as_posix()}")
    return puffer.getvalue()


def bauen(ziel: Path, cache: Path) -> None:
    print(f"Browser-Version {__version__} mit Pyodide {PYODIDE} → {ziel}")
    if ziel.exists():
        shutil.rmtree(ziel)
    py_dir = ziel / "pyodide"
    py_dir.mkdir(parents=True)

    tgz = laden(PYODIDE_TGZ, cache, f"pyodide-{PYODIDE}.tgz", sha512_b64(PYODIDE_SHA512))
    with tarfile.open(fileobj=io.BytesIO(tgz)) as tar:
        for name in PYODIDE_DATEIEN:
            (py_dir / name).write_bytes(tar.extractfile(f"package/{name}").read())
    lock = json.loads((py_dir / "pyodide-lock.json").read_text(encoding="utf-8"))

    for paket in LOCK_PAKETE:
        eintrag = lock["packages"][paket]
        if eintrag.get("depends"):
            raise SystemExit(f"{paket} braucht weitere Pakete: {eintrag['depends']}")
        datei = eintrag["file_name"]
        (py_dir / datei).write_bytes(laden(PYODIDE_CDN + datei, cache, datei, sha256(eintrag["sha256"])))
    for datei, (url, pruefsumme) in PYPI_WHEELS.items():
        (py_dir / datei).write_bytes(laden(url, cache, datei, sha256(pruefsumme)))

    (ziel / "app.zip").write_bytes(app_zip())
    (ziel / "pakete.json").write_text(json.dumps({
        "version": __version__, "pyodide": PYODIDE, "lock": LOCK_PAKETE, "wheels": list(PYPI_WHEELS),
    }, indent=2), encoding="utf-8")
    for name in WEB_DATEIEN:
        text = (ROOT / "web" / name).read_text(encoding="utf-8")
        (ziel / name).write_text(text.replace("__VERSION__", __version__), encoding="utf-8")
    shutil.copy2(ROOT / "einsatzapp" / "icon.png", ziel / "icon.png")
    (ziel / ".nojekyll").write_text("", encoding="utf-8")

    gesamt = sum(p.stat().st_size for p in ziel.rglob("*") if p.is_file())
    print(f"Fertig: {sum(1 for p in ziel.rglob('*') if p.is_file())} Dateien, {gesamt / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ziel", type=Path, default=ROOT / "build" / "web")
    ap.add_argument("--cache", type=Path, default=ROOT / "build" / "web-cache")
    args = ap.parse_args()
    bauen(args.ziel.resolve(), args.cache.resolve())


if __name__ == "__main__":
    main()
