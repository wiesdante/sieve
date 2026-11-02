"""Write ``build/version_info.txt``, the Windows file properties for Sieve.exe."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_version import ROOT, read_version  # noqa: E402

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple},
    prodvers={tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'wiesdante'),
        StringStruct('FileDescription', 'Sieve'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'Sieve'),
        StringStruct('LegalCopyright', 'Copyright (c) wiesdante'),
        StringStruct('OriginalFilename', 'Sieve.exe'),
        StringStruct('ProductName', 'Sieve'),
        StringStruct('ProductVersion', '{version}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> None:
    version = read_version()
    numbers = [int(part) for part in version.split("+")[0].split("-")[0].split(".")[:3]]
    numbers += [0] * (4 - len(numbers))
    out = ROOT / "build" / "version_info.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(TEMPLATE.format(tuple=tuple(numbers), version=version), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
