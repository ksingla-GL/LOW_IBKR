# minimal_aggressive.spec
import sys
sys.setrecursionlimit(5000)

block_cipher = None

a = Analysis(['main.py'],
             pathex=[],
             binaries=[],
             datas=[('config.txt', '.')],
             hiddenimports=['ib_async', 'nest_asyncio', 'asyncio'],
             hookspath=[],
             runtime_hooks=['runtime_hook.py'],
             excludes=[
                 'matplotlib', 'mpl_toolkits', 'tkinter', 'scipy',
                 'notebook', 'ipykernel', 'jupyter', 'jupyterlab',
                 'IPython', 'sphinx', 'babel', 'jinja2', 'PIL',
                 'sklearn', 'pytest', 'nose', 'setuptools.tests',
             ],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

# Remove large binaries
excluded_binaries = [
    'mkl', 'libopenblas', 'scipy', 'matplotlib', 
    'qt5', 'numpy/.libs', 'pandas/_libs/test',
    'tcl', 'tk', 'mpl-data', 'IPython'
]

a.binaries = TOC([x for x in a.binaries if not any(
    excl in x[0].lower() for excl in excluded_binaries
)])

# Minimal data files only
a.datas = [x for x in a.datas if not any(
    excl in str(x[0]).lower() for excl in 
    ['tests', 'test_', 'examples', 'demos', 'benchmark']
)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='low_ibkr',
          debug=False,
          bootloader_ignore_signals=False,
          strip=True,
          upx=True,
          console=True)