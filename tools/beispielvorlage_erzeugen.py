"""Erzeugt die generische Beispielvorlage einsatzapp/beispiel/Musterstadt_LZ1.einsatzvorlage.

Inhalt: Standardtexte aus storage.DEFAULT_TEMPLATE (Zugführerin Sabine Musterfrau, Löschzug 1 der
Feuerwehr Musterstadt) plus frei erfundene Muster-Logos und eine Muster-Unterschrift. Alle Bilder
werden hier mit den mitgelieferten Liberation-Schriften gezeichnet – keine echten Wappen, Logos
oder Unterschriften.

Aufruf im Projektordner:  python tools/beispielvorlage_erzeugen.py
"""

import copy
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from einsatzapp.storage import BEISPIELVORLAGE, DEFAULT_TEMPLATE, Store  # noqa: E402

FONTS = ROOT / "einsatzapp" / "fonts"
ROT, DUNKEL, BLAU, GELB, TINTE = "#c8102e", "#333333", "#1f4e9c", "#f2c230", "#1d3478"


def schrift(name: str, groesse: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), groesse)


def passend(text: str, name: str, max_breite: int, start: int) -> ImageFont.FreeTypeFont:
    groesse = start
    while groesse > 10 and schrift(name, groesse).getlength(text) > max_breite:
        groesse -= 1
    return schrift(name, groesse)


def bezier(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / n for i in range(n + 1))]


def schild(x0, y0, b, h):
    """Wappenschild: oben gerade, unten spitz zulaufend."""
    x1, mitte, knick = x0 + b, x0 + b / 2, y0 + h * 0.55
    return ([(x0, y0), (x1, y0), (x1, knick)] + bezier((x1, knick), (x1, y0 + h * 0.9), (mitte, y0 + h))
            + bezier((mitte, y0 + h), (x0, y0 + h * 0.9), (x0, knick)))


def logo_feuerwehr() -> Image.Image:
    img = Image.new("RGBA", (600, 190), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(schild(8, 8, 140, 174), fill=ROT)
    f = schrift("LiberationSans-Bold.ttf", 44)
    w = f.getlength("LZ 1")
    d.text((78 - w / 2, 52), "LZ 1", font=f, fill="white")
    d.line([(30, 112), (126, 112)], fill="white", width=5)
    d.text((172, 18), "FEUERWEHR", font=passend("FEUERWEHR", "LiberationSans-Bold.ttf", 420, 64), fill=ROT)
    d.text((174, 100), "Musterstadt", font=passend("Musterstadt", "LiberationSans-Regular.ttf", 420, 54),
           fill=DUNKEL)
    return img


def logo_stadt() -> Image.Image:
    img = Image.new("RGBA", (568, 325), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, b, h = 10, 40, 150, 245
    form = schild(x0, y0, b, h)
    maske = Image.new("L", img.size, 0)
    ImageDraw.Draw(maske).polygon(form, fill=255)
    links = Image.new("RGBA", img.size, BLAU)
    rechts = Image.new("RGBA", img.size, GELB)
    teil = Image.new("L", img.size, 0)
    ImageDraw.Draw(teil).rectangle([0, 0, x0 + b / 2, img.size[1]], fill=255)
    flaeche = Image.composite(links, rechts, teil)
    img.paste(flaeche, (0, 0), maske)
    d = ImageDraw.Draw(img)
    # stilisierter Turm
    tx, ty, tb, th = x0 + b / 2 - 30, y0 + 70, 60, 110
    d.rectangle([tx, ty, tx + tb, ty + th], fill="white")
    for i in range(3):
        d.rectangle([tx + i * 24, ty - 16, tx + i * 24 + 12, ty], fill="white")
    d.rectangle([tx + 22, ty + th - 40, tx + tb - 22, ty + th], fill=DUNKEL)
    d.line(form + [form[0]], fill=DUNKEL, width=4)
    d.text((182, 96), "Stadt", font=schrift("LiberationSans-Regular.ttf", 50), fill=DUNKEL)
    d.text((180, 156), "Musterstadt", font=passend("Musterstadt", "LiberationSans-Bold.ttf", 375, 66),
           fill=BLAU)
    return img


def unterschrift() -> Image.Image:
    leinwand = Image.new("RGBA", (1400, 420), (0, 0, 0, 0))
    d = ImageDraw.Draw(leinwand)
    f = schrift("LiberationSansNarrow-Regular.ttf", 190)
    d.text((60, 70), "S. Musterfrau", font=f, fill=TINTE)
    schwung = bezier((70, 320), (650, 410), (1180, 270), n=60)
    d.line(schwung, fill=TINTE, width=7, joint="curve")
    # schräg stellen wie Handschrift
    scher = 0.32
    leinwand = leinwand.transform(leinwand.size, Image.Transform.AFFINE, (1, scher, -scher * 200, 0, 1, 0),
                          resample=Image.Resampling.BICUBIC)
    leinwand = leinwand.crop(leinwand.getbbox())
    breite = 700
    klein = leinwand.resize((breite, round(leinwand.height * breite / leinwand.width)),
                            Image.Resampling.LANCZOS)
    # oben etwas Luft, damit die Unterschrift nicht an „Im Auftrag“ stößt
    fertig = Image.new("RGBA", (breite, klein.height + 45), (0, 0, 0, 0))
    fertig.paste(klein, (0, 45))
    return fertig


def main():
    ziel = ROOT / "einsatzapp" / BEISPIELVORLAGE
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        store = Store(tmp / "daten")
        store.template = copy.deepcopy(DEFAULT_TEMPLATE)
        for slot, bild in (("logo_links", logo_feuerwehr()), ("logo_rechts", logo_stadt()),
                           ("unterschrift", unterschrift())):
            pfad = tmp / f"{slot}.png"
            bild.save(pfad, optimize=True)
            store.template[slot]["datei"] = store.import_image(slot, pfad)
        store.save_template()
        store.export_template(ziel)
    print(f"geschrieben: {ziel.relative_to(ROOT)} ({ziel.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
