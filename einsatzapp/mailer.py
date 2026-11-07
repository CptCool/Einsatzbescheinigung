"""E-Mail-Entwürfe mit PDF-Anhang im Mailprogramm öffnen – niemals selbst senden.

Ein mailto:-Link kann keine Anhänge übergeben, deshalb wird jedes Programm einzeln
angesprochen: Apple Mail/Outlook (macOS) per AppleScript, Outlook (Windows) per COM,
Windows-Standardprogramm per Simple MAPI, Thunderbird per Kommandozeile, Linux per
xdg-email. Rückfallebene: .eml-Dateien mit „X-Unsent: 1“.
"""

import html
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from .placeholders import safe_filename


@dataclass
class Entwurf:
    an: str
    betreff: str
    text: str
    anhaenge: list
    bcc: list = field(default_factory=list)


class MailFehler(Exception):
    pass


PROGRAMME = {
    "auto": "Automatisch (Standard-Mailprogramm)",
    "applemail": "Apple Mail",
    "outlook_mac": "Microsoft Outlook",
    "outlook_win": "Microsoft Outlook (klassisch)",
    "mapi": "Windows-Standard-Mailprogramm (MAPI)",
    "thunderbird": "Thunderbird",
    "xdg": "Linux-Standard-Mailprogramm (xdg-email)",
    "eml": "E-Mail-Dateien (.eml) erzeugen und öffnen",
}

IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
_NO_WINDOW = 0x08000000 if IS_WIN else 0


def verfuegbare_programme() -> list[str]:
    if IS_MAC:
        return ["auto", "applemail", "outlook_mac", "thunderbird", "eml"]
    if IS_WIN:
        return ["auto", "outlook_win", "mapi", "thunderbird", "eml"]
    return ["auto", "xdg", "thunderbird", "eml"]


# =========================================================================== Erkennung

def _mac_mailto_handler() -> str:
    plist = (Path.home() / "Library" / "Preferences" / "com.apple.LaunchServices"
             / "com.apple.launchservices.secure.plist")
    try:
        data = plistlib.loads(plist.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return ""
    for handler in data.get("LSHandlers", []):
        if handler.get("LSHandlerURLScheme") == "mailto":
            return (handler.get("LSHandlerRoleAll") or "").lower()
    return ""


def _win_mailto_progid() -> str:
    try:
        import winreg

        key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return str(winreg.QueryValueEx(k, "ProgId")[0])
    except OSError:
        return ""


def _outlook_com_vorhanden() -> bool:
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"))
        return True
    except OSError:
        return False


def ermittle_auto() -> str:
    """Welches Programm ist als Standard für E-Mails eingestellt?"""
    if IS_MAC:
        handler = _mac_mailto_handler()
        if not handler or handler == "com.apple.mail":
            return "applemail"
        if "outlook" in handler:
            return "outlook_mac"
        if "thunderbird" in handler:
            return "thunderbird"
        return "eml"
    if IS_WIN:
        progid = _win_mailto_progid().lower()
        if "thunderbird" in progid:
            return "thunderbird"
        if "outlook" in progid and _outlook_com_vorhanden():
            return "outlook_win"
        if not progid and _outlook_com_vorhanden():
            return "outlook_win"
        return "mapi"
    if shutil.which("xdg-email"):
        return "xdg"
    if _thunderbird_cmd():
        return "thunderbird"
    return "eml"


def programm_name(key: str) -> str:
    if key == "auto":
        return f"{PROGRAMME['auto']} – erkannt: {PROGRAMME[ermittle_auto()]}"
    return PROGRAMME.get(key, key)


# =========================================================================== macOS

_APPLESCRIPT_ARGS = r'''
	set theSubject to item 1 of argv
	set theBody to item 2 of argv
	set toList to {}
	set bccList to {}
	set fileList to {}
	repeat with i from 3 to count of argv
		set a to item i of argv
		set k to text 1 thru 4 of a
		set v to text 5 thru -1 of a
		if k is "TO::" then
			set end of toList to v
		else if k is "BCC:" then
			set end of bccList to v
		else if k is "ATT:" then
			set end of fileList to (POSIX file v) as alias
		end if
	end repeat
'''

APPLE_MAIL_SCRIPT = "on run argv\n" + _APPLESCRIPT_ARGS + r'''
	tell application "Mail"
		set msg to make new outgoing message with properties {subject:theSubject, content:theBody & linefeed & linefeed, visible:true}
		tell msg
			repeat with addr in toList
				make new to recipient at end of to recipients with properties {address:(addr as text)}
			end repeat
			repeat with addr in bccList
				make new bcc recipient at end of bcc recipients with properties {address:(addr as text)}
			end repeat
			delay 0.3
			repeat with f in fileList
				make new attachment with properties {file name:f} at after the last paragraph
			end repeat
		end tell
		activate
	end tell
end run
'''

OUTLOOK_MAC_SCRIPT = "on run argv\n" + _APPLESCRIPT_ARGS + r'''
	tell application "Microsoft Outlook"
		set msg to make new outgoing message with properties {subject:theSubject, content:theBody}
		repeat with addr in toList
			make new to recipient at msg with properties {email address:{address:(addr as text)}}
		end repeat
		repeat with addr in bccList
			make new bcc recipient at msg with properties {email address:{address:(addr as text)}}
		end repeat
		repeat with f in fileList
			make new attachment at msg with properties {file:f}
		end repeat
		open msg
		activate
	end tell
end run
'''


def _mac_fehlertext(stderr: str, programm: str) -> str:
    if "-1743" in stderr:
        return (f"Keine Berechtigung, {programm} zu steuern. Bitte unter Systemeinstellungen › "
                f"Datenschutz & Sicherheit › Automation erlauben und erneut versuchen.")
    if "-1728" in stderr or "-2700" in stderr or "-10814" in stderr or "-600" in stderr:
        return f"{programm} wurde nicht gefunden oder reagiert nicht."
    return f"{programm}: {stderr.strip() or 'unbekannter Fehler'}"


def _osascript(script: str, entwurf: Entwurf, body: str, programm: str):
    args = [entwurf.betreff, body, f"TO::{entwurf.an}"]
    args += [f"BCC:{b}" for b in entwurf.bcc]
    args += [f"ATT:{Path(a).resolve()}" for a in entwurf.anhaenge]
    try:
        result = subprocess.run(["osascript", "-", *args], input=script, capture_output=True,
                                text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise MailFehler(f"{programm} hat nicht rechtzeitig reagiert "
                         "(evtl. wartet eine Berechtigungsabfrage).") from None
    if result.returncode != 0:
        raise MailFehler(_mac_fehlertext(result.stderr, programm))


# =========================================================================== Windows

_OUTLOOK_PS = r'''
param([string]$JsonPath)
$ErrorActionPreference = 'Stop'
$d = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ol = New-Object -ComObject Outlook.Application
$m = $ol.CreateItem(0)
$m.To = $d.to
if ($d.bcc) { $m.BCC = $d.bcc }
$m.Subject = $d.subject
$m.Body = $d.body
foreach ($a in $d.attachments) { [void]$m.Attachments.Add([string]$a) }
$m.Display($false)
'''


def _outlook_windows(entwurf: Entwurf, tmp: Path):
    script = tmp / "outlook_entwurf.ps1"
    script.write_text(_OUTLOOK_PS, encoding="utf-8-sig")
    data = tmp / "entwurf.json"
    data.write_text(json.dumps({
        "to": entwurf.an, "bcc": "; ".join(entwurf.bcc), "subject": entwurf.betreff,
        "body": entwurf.text.replace("\n", "\r\n"),
        "attachments": [str(Path(a).resolve()) for a in entwurf.anhaenge],
    }, ensure_ascii=False), encoding="utf-8")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), str(data)],
            capture_output=True, text=True, timeout=180, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise MailFehler("Outlook hat nicht rechtzeitig reagiert.") from None
    if result.returncode != 0:
        msg = (result.stderr or result.stdout).strip().splitlines()
        raise MailFehler("Outlook (klassisch) konnte nicht angesteuert werden: "
                         + (msg[0] if msg else "unbekannter Fehler")
                         + " – Hinweis: Das „neue Outlook“ unterstützt das nicht; "
                           "dann bitte „.eml-Dateien“ wählen.")


def _mapi_windows(entwurf: Entwurf):
    import ctypes
    from ctypes import wintypes

    class RecipDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("ulRecipClass", wintypes.ULONG),
                    ("lpszName", wintypes.LPWSTR), ("lpszAddress", wintypes.LPWSTR),
                    ("ulEIDSize", wintypes.ULONG), ("lpEntryID", ctypes.c_void_p)]

    class FileDesc(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("flFlags", wintypes.ULONG),
                    ("nPosition", wintypes.ULONG), ("lpszPathName", wintypes.LPWSTR),
                    ("lpszFileName", wintypes.LPWSTR), ("lpFileType", ctypes.c_void_p)]

    class Message(ctypes.Structure):
        _fields_ = [("ulReserved", wintypes.ULONG), ("lpszSubject", wintypes.LPWSTR),
                    ("lpszNoteText", wintypes.LPWSTR), ("lpszMessageType", wintypes.LPWSTR),
                    ("lpszDateReceived", wintypes.LPWSTR), ("lpszConversationID", wintypes.LPWSTR),
                    ("flFlags", wintypes.ULONG), ("lpOriginator", ctypes.POINTER(RecipDesc)),
                    ("nRecipCount", wintypes.ULONG), ("lpRecips", ctypes.POINTER(RecipDesc)),
                    ("nFileCount", wintypes.ULONG), ("lpFiles", ctypes.POINTER(FileDesc))]

    MAPI_TO, MAPI_BCC = 1, 3
    MAPI_LOGON_UI, MAPI_DIALOG_MODELESS, MAPI_DIALOG = 0x1, 0x4, 0x8
    recips = [(MAPI_TO, entwurf.an)] + [(MAPI_BCC, b) for b in entwurf.bcc]
    recip_arr = (RecipDesc * len(recips))(
        *[RecipDesc(0, cls, addr, f"SMTP:{addr}", 0, None) for cls, addr in recips])
    files = [Path(a).resolve() for a in entwurf.anhaenge]
    file_arr = (FileDesc * max(1, len(files)))(
        *[FileDesc(0, 0, 0xFFFFFFFF, str(p), p.name, None) for p in files])
    msg = Message(0, entwurf.betreff, entwurf.text.replace("\n", "\r\n"), None, None, None, 0,
                  None, len(recips), ctypes.cast(recip_arr, ctypes.POINTER(RecipDesc)),
                  len(files), ctypes.cast(file_arr, ctypes.POINTER(FileDesc)) if files else None)
    try:
        send = ctypes.WinDLL("mapi32.dll").MAPISendMailW
    except (OSError, AttributeError):
        raise MailFehler("Auf diesem PC ist kein MAPI-fähiges Mailprogramm eingerichtet.") from None
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(Message),
                     wintypes.ULONG, wintypes.ULONG]
    send.restype = wintypes.ULONG
    rc = send(None, None, ctypes.byref(msg), MAPI_LOGON_UI | MAPI_DIALOG | MAPI_DIALOG_MODELESS, 0)
    if rc not in (0, 1):  # 1 = vom Nutzer abgebrochen (nicht gesendet) – kein Fehler
        rc = send(None, None, ctypes.byref(msg), MAPI_LOGON_UI | MAPI_DIALOG, 0)
    if rc not in (0, 1):
        raise MailFehler(f"Das Standard-Mailprogramm hat den Entwurf abgelehnt (MAPI-Code {rc}). "
                         "Bitte Outlook/Thunderbird als Standard festlegen oder „.eml-Dateien“ wählen.")


# =========================================================================== Thunderbird

def _thunderbird_cmd() -> list[str] | None:
    if IS_MAC:
        for base in (Path("/Applications"), Path.home() / "Applications"):
            exe = base / "Thunderbird.app" / "Contents" / "MacOS" / "thunderbird"
            if exe.exists():
                return [str(exe)]
        return None
    if IS_WIN:
        try:
            import winreg

            key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\thunderbird.exe"
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        exe = winreg.QueryValueEx(k, "")[0]
                        if exe and Path(exe).exists():
                            return [exe]
                except OSError:
                    continue
        except ImportError:
            pass
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                exe = Path(base) / "Mozilla Thunderbird" / "thunderbird.exe"
                if exe.exists():
                    return [str(exe)]
        return None
    for name in ("thunderbird", "thunderbird-esr"):
        exe = shutil.which(name)
        if exe:
            return [exe]
    if shutil.which("flatpak"):
        ok = subprocess.run(["flatpak", "info", "org.mozilla.Thunderbird"],
                            capture_output=True).returncode == 0
        if ok:
            return ["flatpak", "run", "org.mozilla.Thunderbird"]
    return None


def _thunderbird_laeuft() -> bool:
    try:
        if IS_WIN:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq thunderbird.exe", "/NH"],
                                 capture_output=True, text=True, creationflags=_NO_WINDOW).stdout
            return "thunderbird.exe" in out.lower()
        return subprocess.run(["pgrep", "-i", "thunderbird"], capture_output=True).returncode == 0
    except OSError:
        return True  # im Zweifel nicht warten


def _tb_quote(value: str) -> str:
    return "'" + value.replace("'", "’") + "'"


# =========================================================================== .eml

def schreibe_eml(entwurf: Entwurf, ordner: Path) -> Path:
    msg = EmailMessage()
    msg["To"] = entwurf.an
    if entwurf.bcc:
        msg["Bcc"] = ", ".join(entwurf.bcc)
    msg["Subject"] = entwurf.betreff
    msg["Date"] = formatdate(localtime=True)
    msg["X-Unsent"] = "1"  # Outlook öffnet die Datei als bearbeitbaren Entwurf
    msg.set_content(entwurf.text)
    for a in entwurf.anhaenge:
        p = Path(a)
        msg.add_attachment(p.read_bytes(), maintype="application", subtype="pdf", filename=p.name)
    ordner.mkdir(parents=True, exist_ok=True)
    stem = Path(entwurf.anhaenge[0]).stem if entwurf.anhaenge else safe_filename(entwurf.betreff)
    path = ordner / f"{stem}.eml"
    path.write_bytes(bytes(msg))
    return path


def _oeffnen(path: Path):
    if IS_MAC:
        subprocess.run(["open", str(path)], check=False)
    elif IS_WIN:
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])


# =========================================================================== Mailer

class Mailer:
    """Erstellt Entwürfe nacheinander. ``arbeitsordner`` nimmt Hilfsdateien auf
    (Thunderbird-Texte, .eml-Dateien) und sollte im Benutzerordner liegen."""

    def __init__(self, programm: str, arbeitsordner: Path):
        self.auto = programm == "auto"
        self.programm = ermittle_auto() if self.auto else programm
        self.ordner = Path(arbeitsordner)
        self._tmp = Path(tempfile.mkdtemp(prefix="einsatzbescheinigung_mail_"))
        self._tb_gestartet = False

    @property
    def name(self) -> str:
        return PROGRAMME.get(self.programm, self.programm)

    def erstelle(self, entwurf: Entwurf) -> str:
        """Entwurf öffnen. Liefert eine kurze Beschreibung, wirft MailFehler."""
        try:
            return self._erstelle(self.programm, entwurf)
        except MailFehler as err:
            if self.auto and self.programm != "eml":
                self._eml(entwurf)
                return f"als .eml-Datei geöffnet ({err})"
            raise
        except Exception as err:  # unerwartete Fehler einheitlich melden
            raise MailFehler(f"{self.name}: {err}") from err

    def _erstelle(self, programm: str, entwurf: Entwurf) -> str:
        if programm == "applemail":
            _osascript(APPLE_MAIL_SCRIPT, entwurf, entwurf.text, "Apple Mail")
        elif programm == "outlook_mac":
            body = html.escape(entwurf.text).replace("\n", "<br>\n")
            _osascript(OUTLOOK_MAC_SCRIPT, entwurf, f"<div>{body}</div>", "Microsoft Outlook")
        elif programm == "outlook_win":
            _outlook_windows(entwurf, self._tmp)
        elif programm == "mapi":
            _mapi_windows(entwurf)
        elif programm == "thunderbird":
            self._thunderbird(entwurf)
        elif programm == "xdg":
            self._xdg(entwurf)
        elif programm == "eml":
            self._eml(entwurf)
            return "als .eml-Datei geöffnet"
        else:
            raise MailFehler(f"Unbekanntes Mailprogramm: {programm}")
        return "Entwurf geöffnet"

    def _thunderbird(self, entwurf: Entwurf):
        cmd = _thunderbird_cmd()
        if not cmd:
            raise MailFehler("Thunderbird wurde nicht gefunden.")
        textdir = self.ordner / ".mailtexte"
        textdir.mkdir(parents=True, exist_ok=True)
        stem = Path(entwurf.anhaenge[0]).stem if entwurf.anhaenge else "mail"
        textfile = textdir / f"{stem}.txt"
        textfile.write_text(entwurf.text, encoding="utf-8")
        parts = [f"to={_tb_quote(entwurf.an)}"]
        if entwurf.bcc:
            parts.append(f"bcc={_tb_quote(','.join(entwurf.bcc))}")
        parts.append(f"subject={_tb_quote(entwurf.betreff)}")
        parts.append(f"message={_tb_quote(str(textfile.resolve()))}")
        if entwurf.anhaenge:
            uris = ",".join(Path(a).resolve().as_uri() for a in entwurf.anhaenge)
            parts.append(f"attachment={_tb_quote(uris)}")
        war_aktiv = self._tb_gestartet or _thunderbird_laeuft()
        try:
            subprocess.Popen([*cmd, "-compose", ",".join(parts)], creationflags=_NO_WINDOW)
        except OSError as err:
            raise MailFehler(f"Thunderbird konnte nicht gestartet werden: {err}") from None
        if not war_aktiv:
            # Beim Kaltstart warten, sonst starten weitere Aufrufe eine zweite Instanz.
            for _ in range(30):
                time.sleep(1)
                if _thunderbird_laeuft():
                    break
            time.sleep(4)
        else:
            time.sleep(0.8)
        self._tb_gestartet = True

    def _xdg(self, entwurf: Entwurf):
        if not shutil.which("xdg-email"):
            raise MailFehler("xdg-email ist nicht installiert (Paket xdg-utils).")
        cmd = ["xdg-email", "--utf8", "--subject", entwurf.betreff, "--body", entwurf.text]
        for b in entwurf.bcc:
            cmd += ["--bcc", b]
        for a in entwurf.anhaenge:
            cmd += ["--attach", str(Path(a).resolve())]
        cmd.append(entwurf.an)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise MailFehler(f"xdg-email: {result.stderr.strip() or 'Fehler ' + str(result.returncode)}")
        time.sleep(0.5)

    def _eml(self, entwurf: Entwurf) -> Path:
        path = schreibe_eml(entwurf, self.ordner / "E-Mail-Entwürfe")
        _oeffnen(path)
        time.sleep(0.3)
        return path
