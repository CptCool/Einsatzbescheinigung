# PyInstaller-Rezept: pyinstaller --noconfirm einsatzbescheinigung.spec
# macOS -> dist/Einsatzbescheinigung.app · Windows/Linux -> dist/Einsatzbescheinigung(.exe)
import sys

sys.path.insert(0, ".")
from einsatzapp import __version__  # noqa: E402

NAME = "Einsatzbescheinigung"
ICON = "einsatzapp/icon.png"

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("einsatzapp/fonts", "einsatzapp/fonts"), ("einsatzapp/beispiel", "einsatzapp/beispiel"),
           ("einsatzapp/icon.png", "einsatzapp")],
    hiddenimports=["PIL._tkinter_finder"],
    excludes=["numpy", "matplotlib", "pytest", "IPython"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon=ICON)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=ICON,
        bundle_identifier="de.feuerwehr.einsatzbescheinigung",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "CFBundleDevelopmentRegion": "de",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSAppleEventsUsageDescription":
                "Die App legt E-Mail-Entwürfe mit der Bescheinigung als Anhang in Apple Mail "
                "oder Outlook an. Gesendet wird nur durch Sie selbst.",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, icon=ICON,
              upx=False)
