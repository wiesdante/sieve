# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build definition. Run: pyinstaller sieve.spec --noconfirm --clean
from pathlib import Path

ROOT = Path(SPECPATH)
VERSION_INFO = ROOT / "build" / "version_info.txt"

a = Analysis(
    [str(ROOT / "src" / "sieve" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=["socks"],
    excludes=["tkinter", "unittest", "pydoc", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sieve",
    console=False,
    icon=str(ROOT / "assets" / "icon.ico"),
    version=str(VERSION_INFO) if VERSION_INFO.exists() else None,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Sieve", upx=False)
