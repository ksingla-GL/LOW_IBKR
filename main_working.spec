# -*- mode: python ; coding: utf-8 -*-
# This spec file replicates the working command:
# pyinstaller --onefile main.py --exclude-module IPython --exclude-module sphinx --exclude-module babel --exclude-module jinja2 --exclude-module jedi --exclude-module astroid --clean

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('config.txt', '.')],
    hiddenimports=['nest_asyncio', 'ib_insync', 'eventkit'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Only exclude the problematic modules that work in your command
        'IPython', 
        'sphinx', 
        'babel', 
        'jinja2', 
        'jedi', 
        'astroid'
    ],
    noarchive=False,
    optimize=0,  # No optimization to match simple command
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # No compression to match simple command
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)