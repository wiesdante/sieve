# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build definition. Run: pyinstaller sieve.spec --noconfirm --clean
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# PyMuPDF ships native libraries; collect everything so PDF reading works in the build.
pdf_datas, pdf_binaries, pdf_hidden = collect_all("pymupdf")
# Playwright drives the Edge/Chrome already installed on the PC; only its driver is bundled.
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

ROOT = Path(SPECPATH)
VERSION_INFO = ROOT / "build" / "version_info.txt"

a = Analysis(
    [str(ROOT / "src" / "sieve" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "assets"), "assets"), *pdf_datas, *pw_datas],
    binaries=[*pdf_binaries, *pw_binaries],
    hiddenimports=["socks", *pdf_hidden, *pw_hidden],
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
