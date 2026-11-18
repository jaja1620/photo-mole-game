# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for photo-mole-game-installer.
# Portable: the skill payload is resolved relative to this file (../skill),
# or overridden with the PMG_SKILL_PAYLOAD environment variable.
# Build:  python -m PyInstaller --clean -y photo-mole-game-installer.spec
# Or just use build.ps1 / build.bat, which pass --add-data explicitly.

import os

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821  (SPEC is provided by PyInstaller)
_payload = os.environ.get("PMG_SKILL_PAYLOAD") or os.path.normpath(os.path.join(_SPEC_DIR, "..", "skill"))
_payload = os.path.abspath(_payload)

if not os.path.isfile(os.path.join(_payload, "SKILL.md")):
    raise SystemExit(
        "skill payload not found: %s\n"
        "Expected a photo-mole-game skill directory (containing SKILL.md) at ../skill, "
        "or set PMG_SKILL_PAYLOAD to its absolute path." % _payload
    )

a = Analysis(
    ['photo_mole_installer.py'],
    pathex=[],
    binaries=[],
    datas=[(_payload, 'skill_payload/photo-mole-game')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='photo-mole-game-installer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
