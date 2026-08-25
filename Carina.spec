# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

# ADR-012: tudo local após a instalação — dados processados (catálogos,
# banco de céu profundo, imagens M/C) e a efeméride JPL embarcados.
datas = [
    ('data/processed', 'data/processed'),
    ('data/ephemeris', 'data/ephemeris'),
]
hiddenimports = []
datas += collect_data_files('skyfield')
# tzdata: o Windows não tem a base IANA — o zoneinfo precisa dela para os
# fusos horários das cidades (base local de localização do observador)
datas += collect_data_files('tzdata')
hiddenimports += collect_submodules('OpenGL')
hiddenimports += collect_submodules('tzdata')


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='Carina',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Carina',
)
