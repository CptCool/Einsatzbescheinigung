"""Datums-/Zeitformate, Eingabe-Parser und Platzhalter-Ersetzung."""

import re
import unicodedata
from datetime import date, datetime, time, timedelta

MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


# --------------------------------------------------------------------------- Formate

def fmt_date(d) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


def fmt_time(t) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def fmt_long_date(d) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def fmt_duration(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes // 60}:{minutes % 60:02d} Std."


# --------------------------------------------------------------------------- Parser

def parse_date(text: str, default_year: int | None = None) -> date:
    """Akzeptiert 07.04.2026, 7.4.26, 7.4. (aktuelles Jahr), 070426, 2026-04-07."""
    s = (text or "").strip()
    if not s:
        raise ValueError("Bitte ein Datum eingeben (TT.MM.JJJJ).")
    year = month = day = None
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
        year, month, day = int(m[1]), int(m[2]), int(m[3])
    elif m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})?", s):
        day, month = int(m[1]), int(m[2])
        if m[3] is None:
            year = default_year or date.today().year
        else:
            year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
    elif m := re.fullmatch(r"(\d{2})(\d{2})(\d{2}|\d{4})", s):
        day, month = int(m[1]), int(m[2])
        year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
    if year is None:
        raise ValueError(f"„{text}“ ist kein gültiges Datum (Format TT.MM.JJJJ).")
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"„{text}“ ist kein gültiges Datum.") from None


def parse_time(text: str) -> time:
    """Akzeptiert 11:59, 11.59, 1159, 959, 11, „11:59 Uhr“."""
    s = re.sub(r"\s*(uhr|h)$", "", (text or "").strip().lower())
    s = s.replace(".", ":").replace(",", ":")
    if re.fullmatch(r"\d{1,2}", s):
        hour, minute = int(s), 0
    elif re.fullmatch(r"\d{3,4}", s):
        hour, minute = int(s[:-2]), int(s[-2:])
    elif m := re.fullmatch(r"(\d{1,2}):(\d{2})", s):
        hour, minute = int(m[1]), int(m[2])
    else:
        raise ValueError(f"„{text}“ ist keine gültige Uhrzeit (Format HH:MM).")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"„{text}“ ist keine gültige Uhrzeit.")
    return time(hour, minute)


def combine(date_text: str, time_text: str) -> datetime:
    return datetime.combine(parse_date(date_text), parse_time(time_text))


# --------------------------------------------------------------------------- Kontext

def gender_index(anrede: str) -> int:
    """0 = männlich (Herr), 1 = weiblich (Frau), 2 = keine Angabe."""
    return {"herr": 0, "frau": 1}.get((anrede or "").strip().lower(), 2)


def _ende_text(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return fmt_time(end)
    return f"{fmt_date(end)}, {fmt_time(end)}"


def _zeitraum(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f"am {fmt_date(start)} von {fmt_time(start)} Uhr bis {fmt_time(end)} Uhr"
    return (f"vom {fmt_date(start)}, {fmt_time(start)} Uhr "
            f"bis zum {fmt_date(end)}, {fmt_time(end)} Uhr")


def build_context(contact: dict, einsatznummer: str, einsatz_start: datetime,
                  einsatz_end: datetime, start: datetime, end: datetime,
                  ausstellungsdatum: date) -> dict:
    """Alle Platzhalterwerte für eine Person bei einem Einsatz."""
    anrede = (contact.get("anrede") or "").strip()
    vorname = (contact.get("vorname") or "").strip()
    nachname = (contact.get("nachname") or "").strip()
    ctx = {
        "Anrede": anrede if gender_index(anrede) < 2 else "",
        "Vorname": vorname,
        "Nachname": nachname,
        "Name": f"{vorname} {nachname}".strip(),
        "Dienstgrad": (contact.get("dienstgrad") or "").strip(),
        "Straße": (contact.get("strasse") or "").strip(),
        "PLZ": (contact.get("plz") or "").strip(),
        "Ort": (contact.get("ort") or "").strip(),
        "EMail": (contact.get("email") or "").strip(),
        "Einsatznummer": (einsatznummer or "").strip(),
        "Datum": fmt_date(start),
        "Beginn": fmt_time(start),
        "Ende": _ende_text(start, end),
        "EndeDatum": fmt_date(end),
        "EndeZeit": fmt_time(end),
        "Dauer": fmt_duration(end - start),
        "Zeitraum": _zeitraum(start, end),
        "EinsatzDatum": fmt_date(einsatz_start),
        "EinsatzBeginn": fmt_time(einsatz_start),
        "EinsatzEnde": _ende_text(einsatz_start, einsatz_end),
        "EinsatzDatumISO": einsatz_start.strftime("%Y-%m-%d"),
        "EinsatzBeginnHHMM": einsatz_start.strftime("%H%M"),
        "Ausstellungsdatum": fmt_long_date(ausstellungsdatum),
        "AusstellungsdatumKurz": fmt_date(ausstellungsdatum),
        "Jahr": str(einsatz_start.year),
    }
    # Alternative Schreibweisen
    ctx["Strasse"] = ctx["Straße"]
    ctx["E-Mail"] = ctx["EMail"]
    ctx["Email"] = ctx["EMail"]
    return ctx


DEMO_KONTAKT = {
    "anrede": "Herr", "vorname": "Max", "nachname": "Mustermann", "dienstgrad": "OFM",
    "strasse": "Musterstraße 1", "plz": "12345", "ort": "Musterstadt",
    "email": "max.mustermann@example.org",
}


def demo_context() -> tuple[dict, int]:
    start = datetime(2026, 4, 7, 11, 59)
    end = datetime(2026, 4, 7, 15, 0)
    ctx = build_context(DEMO_KONTAKT, "2026-117", start, end, start, end, date(2026, 4, 9))
    return ctx, 0


# Für die Hilfe-Liste in der Vorlage: (Platzhalter, Bedeutung)
PLATZHALTER_HILFE = [
    ("{Anrede}", "Herr / Frau"),
    ("{Herrn/Frau}", "Anschrift: „Herrn“ bzw. „Frau“"),
    ("{Herr/Frau}", "im Text: „Herr“ bzw. „Frau“"),
    ("{seiner/ihrer}", "beliebige Form männlich/weiblich[/ohne Angabe]"),
    ("{Vorname}", "Vorname"),
    ("{Nachname}", "Nachname"),
    ("{Name}", "Vor- und Nachname"),
    ("{Dienstgrad}", "z. B. OFM"),
    ("{Straße}", "Straße und Hausnummer"),
    ("{PLZ}", "Postleitzahl"),
    ("{Ort}", "Wohnort"),
    ("{EMail}", "E-Mail-Adresse"),
    ("{Einsatznummer}", "wie im Einsatz eingetragen"),
    ("{Datum}", "Einsatztag der Person, 07.04.2026"),
    ("{Beginn}", "Beginn der Person, 11:59"),
    ("{Ende}", "Ende der Person, 15:00 (mit Datum, falls Folgetag)"),
    ("{Dauer}", "z. B. 3:01 Std."),
    ("{Zeitraum}", "„am 07.04.2026 von 11:59 Uhr bis 15:00 Uhr“"),
    ("{EinsatzDatum}", "Datum des Einsatzbeginns"),
    ("{EinsatzBeginn}", "Uhrzeit des Einsatzbeginns"),
    ("{EinsatzEnde}", "Uhrzeit des Einsatzendes"),
    ("{EinsatzDatumISO}", "2026-04-07 (für Dateinamen)"),
    ("{EinsatzBeginnHHMM}", "1159 (für Dateinamen)"),
    ("{Ausstellungsdatum}", "9. April 2026"),
    ("{AusstellungsdatumKurz}", "09.04.2026"),
    ("{Jahr}", "Jahr des Einsatzes"),
]

_PLACEHOLDER = re.compile(r"\{([^{}\n]+)\}")
_MULTISPACE = re.compile(r"(?<=\S)[ \t]{2,}")


def render(text: str, ctx: dict, gender: int, unknown: set | None = None) -> str:
    """Platzhalter ersetzen. ``{a/b[/c]}`` wählt die Form nach Anrede (Herr/Frau/keine)."""
    lookup = {k.lower(): v for k, v in ctx.items()}

    def repl(match):
        key = match.group(1).strip()
        value = lookup.get(key.lower())
        if value is not None:
            return value
        if "/" in key:
            forms = [f.strip() for f in key.split("/")]
            return forms[gender] if gender < len(forms) else ""
        if unknown is not None:
            unknown.add("{" + key + "}")
        return match.group(0)

    out = _PLACEHOLDER.sub(repl, text or "")
    lines = [_MULTISPACE.sub(" ", line).rstrip() for line in out.split("\n")]
    return "\n".join(lines)


def safe_filename(name: str) -> str:
    """Dateiname ohne verbotene Zeichen; Leerzeichen werden zu Unterstrichen."""
    name = unicodedata.normalize("NFC", name or "")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name)
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"_{2,}", "_", name).strip("._- ")
    return name[:180] or "Bescheinigung"
