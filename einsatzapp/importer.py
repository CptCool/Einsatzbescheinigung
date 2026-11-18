"""Kontakte aus CSV- oder Excel-Dateien einlesen (mit automatischer Spaltenzuordnung)."""

import csv
import io
import re
from pathlib import Path

ZIELFELDER = [
    ("anrede", "Anrede"),
    ("dienstgrad", "Dienstgrad"),
    ("vorname", "Vorname"),
    ("nachname", "Nachname"),
    ("name_komplett", "Name komplett (Vor- + Nachname)"),
    ("strasse", "Straße"),
    ("hausnummer", "Hausnummer"),
    ("plz", "PLZ"),
    ("ort", "Ort"),
    ("plz_ort", "PLZ + Ort zusammen"),
    ("email", "E-Mail"),
]

_SYNONYME = {
    "anrede": ["anrede", "geschlecht", "salutation"],
    "dienstgrad": ["dienstgrad", "dg", "rang", "dienstgradabkürzung", "dienstgrad kurz"],
    "vorname": ["vorname", "rufname", "first name", "firstname", "given name"],
    "nachname": ["nachname", "familienname", "zuname", "last name", "lastname", "surname"],
    "name_komplett": ["name", "vollständiger name", "kamerad", "kameradin", "mitglied", "person"],
    "strasse": ["straße", "strasse", "str", "straße und hausnummer", "straße hausnummer",
                "straße nr", "adresse", "anschrift", "street"],
    "hausnummer": ["hausnummer", "hausnr", "nr", "hnr"],
    "plz": ["plz", "postleitzahl", "zip"],
    "ort": ["ort", "wohnort", "stadt", "city"],
    "plz_ort": ["plz ort", "plz und ort", "plzort"],
    "email": ["e-mail", "email", "mail", "e-mail-adresse", "emailadresse", "e-mail adresse",
              "mailadresse", "e-mailadresse"],
}


def _norm(header: str) -> str:
    h = (header or "").strip().lower()
    h = re.sub(r"[._/:\-]+", " ", h)
    h = re.sub(r"\s+", " ", h).strip()
    return h


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def lese_tabelle(path: Path) -> tuple[list[str], list[list[str]]]:
    """Liest die erste Tabelle einer .xlsx/.csv-Datei: (Spaltenköpfe, Zeilen)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    elif suffix == ".xls":
        raise ValueError("Das alte Excel-Format .xls wird nicht unterstützt. "
                         "Bitte in Excel als .xlsx oder .csv speichern.")
    else:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:5000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]

    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        raise ValueError("Die Datei enthält keine Daten.")
    headers = rows[0]
    width = max(len(r) for r in rows)
    headers = [h or f"Spalte {i + 1}" for i, h in enumerate(headers + [""] * (width - len(headers)))]
    data = [r + [""] * (width - len(r)) for r in rows[1:]]
    return headers, data


def auto_zuordnung(headers: list[str]) -> dict[str, int | None]:
    """Ordnet Zielfelder anhand typischer Spaltennamen zu (Index der Spalte oder None)."""
    normed = [_norm(h) for h in headers]
    mapping: dict[str, int | None] = {key: None for key, _ in ZIELFELDER}
    taken: set[int] = set()
    for key, _ in ZIELFELDER:
        for syn in map(_norm, _SYNONYME[key]):  # gleich normalisieren wie die Spaltenköpfe
            if syn in normed and normed.index(syn) not in taken:
                mapping[key] = normed.index(syn)
                taken.add(mapping[key])
                break
    # „Name“ neben „Vorname“ ist meist der Nachname
    if mapping["name_komplett"] is not None and mapping["vorname"] is not None \
            and mapping["nachname"] is None:
        mapping["nachname"], mapping["name_komplett"] = mapping["name_komplett"], None
    return mapping


def _anrede(value: str) -> str:
    v = value.strip().lower().rstrip(".")
    if v in ("herr", "herrn", "hr", "m", "männlich", "maennlich", "mann"):
        return "Herr"
    if v in ("frau", "fr", "w", "weiblich", "f"):
        return "Frau"
    return ""


def wende_an(headers: list[str], rows: list[list[str]], mapping: dict[str, int | None]) -> list[dict]:
    """Erzeugt Kontakte aus den Zeilen gemäß Zuordnung."""
    contacts = []
    for row in rows:
        def get(key):
            idx = mapping.get(key)
            return row[idx].strip() if idx is not None and idx < len(row) else ""

        c = {
            "anrede": _anrede(get("anrede")),
            "dienstgrad": get("dienstgrad"),
            "vorname": get("vorname"),
            "nachname": get("nachname"),
            "strasse": get("strasse"),
            "plz": get("plz"),
            "ort": get("ort"),
            "email": get("email"),
        }
        full = get("name_komplett")
        if full and not (c["vorname"] or c["nachname"]):
            if "," in full:
                nach, vor = [p.strip() for p in full.split(",", 1)]
            else:
                parts = full.split()
                vor, nach = " ".join(parts[:-1]), parts[-1] if parts else ""
            c["vorname"], c["nachname"] = vor, nach
        if get("hausnummer"):
            c["strasse"] = f"{c['strasse']} {get('hausnummer')}".strip()
        plz_ort = get("plz_ort")
        if plz_ort and not (c["plz"] or c["ort"]):
            m = re.match(r"(\d{4,5})\s+(.*)", plz_ort)
            c["plz"], c["ort"] = (m[1], m[2]) if m else ("", plz_ort)
        if c["plz"].isdigit() and len(c["plz"]) == 4:
            c["plz"] = "0" + c["plz"]  # Excel verliert führende Nullen
        if c["vorname"] or c["nachname"]:
            contacts.append(c)
    return contacts


def exportiere_csv(contacts: list[dict], path: Path):
    """Kontakte als Excel-freundliche CSV (Semikolon, UTF-8 mit BOM) speichern."""
    cols = [("anrede", "Anrede"), ("dienstgrad", "Dienstgrad"), ("vorname", "Vorname"),
            ("nachname", "Nachname"), ("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort"),
            ("email", "E-Mail")]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([label for _, label in cols])
        for c in contacts:
            w.writerow([c.get(key, "") for key, _ in cols])
