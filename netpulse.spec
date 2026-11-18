# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a one-folder, windowed NetPulse build.

Build with:

    python -m PyInstaller netpulse.spec --noconfirm

The entry script is ``app/__main__.py`` and the repository root is added to
``pathex`` so that ``import app`` resolves while PyInstaller analyses the code.
The resulting executable is written to ``dist/NetPulse/NetPulse.exe``.
"""

from pathlib import Path

# SPECPATH is provided by PyInstaller and points at the directory containing this
# spec file, which is the repository root. Adding it to pathex lets PyInstaller
# resolve ``import app...`` imports from the sources in place.
PROJECT_ROOT = Path(SPECPATH).resolve()

a = Analysis(
    [str(PROJECT_ROOT / "app" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],
    # psutil is imported directly and is a required runtime dependency.
    # dnspython is optional: NetPulse degrades gracefully without it, so "dns" is
    # not listed here. Add "dns" to this list if you install dnspython in the
    # build environment and want per-server DNS timing bundled.
    hiddenimports=["psutil"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the build lean: exclude the Tk GUI toolkit and the test tooling.
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NetPulse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression is disabled: it can trigger antivirus false positives and
    # PySide6 binaries are more reliable uncompressed.
    upx=False,
    # Windowed build: no console window is shown.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # No icon yet. To add one later, place an .ico file in the repository and
    # set icon="assets/netpulse.ico" (or another path) here.
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NetPulse",
)
