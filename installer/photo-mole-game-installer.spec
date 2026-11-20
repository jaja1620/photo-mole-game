# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['photo_mole_installer.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/2013083/AppData/Roaming/Tencent/Marvis/User/oAN1i2a0fVAITIdl93aRLTkg_DYY/workspace/conv_98ebfacfe330491d91792ce5ac9c282c/output/photo-mole-installer/payload/photo-mole-game', 'skill_payload/photo-mole-game')],
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
