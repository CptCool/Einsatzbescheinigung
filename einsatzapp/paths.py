"""Plattformabhängige Pfade und Hilfen zum Öffnen von Dateien/Ordnern."""

import os
import subprocess
import sys
from pathlib import Path

from . import APP_NAME


def resource_dir() -> Path:
    """Ordner mit mitgelieferten Dateien (Schriften, Icon) – auch im PyInstaller-Paket."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "einsatzapp"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Ordner für Kontakte, Vorlage und Einstellungen des Nutzers."""
    override = os.environ.get("EINSATZBESCHEINIGUNG_DATEN")
    if override:
        path = Path(override)
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.name == "nt":
        path = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "einsatzbescheinigung"
    path.mkdir(parents=True, exist_ok=True)
    return path


def documents_dir() -> Path:
    """Der „Dokumente“-Ordner des Nutzers (berücksichtigt OneDrive-Umleitung unter Windows)."""
    if os.name == "nt":
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                value, _ = winreg.QueryValueEx(k, "Personal")
            path = Path(os.path.expandvars(value))
            if path.is_dir():
                return path
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        try:
            out = subprocess.run(
                ["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            if out and Path(out).is_dir() and Path(out) != Path.home():
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    path = Path.home() / "Documents"
    return path if path.is_dir() else Path.home()


def open_path(path) -> None:
    """Datei oder Ordner mit dem Standardprogramm des Systems öffnen."""
    path = str(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # noqa: S606 – Windows-Standardaufruf
    else:
        subprocess.Popen(["xdg-open", path])
