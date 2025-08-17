# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('config.txt', '.')],
    hiddenimports=['nest_asyncio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy unused modules
        'IPython', 'sphinx', 'babel', 'jinja2', 'jedi', 'astroid',
        # Core heavy libraries - more aggressive exclusion
        'numpy', 'pandas', 'scipy', 'sklearn', 'tensorflow', 'torch', 'cv2',
        # Pandas/numpy sub-modules
        'pandas.plotting', 'pandas.io.formats.style', 'pandas.tests',
        'numpy.tests', 'numpy.distutils', 'numpy.f2py', 'numpy.core',
        # Matplotlib (if not needed)
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends',
        # GUI frameworks
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        # Development tools
        'pytest', 'setuptools', 'wheel', 'pip',
        # Documentation
        'docutils', 'markupsafe',
        # Unused pandas extensions
        'pandas_ta', 'ta-lib',
        # Additional heavy modules
        'certifi.cacert', 'dateutil', 'pytz'
    ],
    noarchive=False,
    optimize=2,  # Higher optimization
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
    strip=True,  # Strip debug symbols
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)