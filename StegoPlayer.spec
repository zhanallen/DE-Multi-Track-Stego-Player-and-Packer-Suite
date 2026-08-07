# -*- mode: python ; coding: utf-8 -*-
import os
import glob
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all for numba, llvmlite, cv2, imageio_ffmpeg
numba_datas, numba_binaries, numba_hiddenimports = collect_all('numba')
llvmlite_datas, llvmlite_binaries, llvmlite_hiddenimports = collect_all('llvmlite')
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all('cv2')
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all('imageio_ffmpeg')

# Find VC Runtime DLLs in PySide6 package
pyside6_dir = os.path.join('.venv', 'Lib', 'site-packages', 'PySide6')
dll_files = glob.glob(os.path.join(pyside6_dir, '*140*.dll'))
vc_binaries = [(dll, '.') for dll in dll_files]

db_files = []
country_db = os.path.join('for_ip', 'i18n_security', 'data', 'dbip-country-lite.mmdb')
if os.path.exists(country_db):
    db_files.append((country_db, 'for_ip/i18n_security/data'))
city_db = os.path.join('for_ip', 'i18n_security', 'data', 'dbip-city-lite.mmdb')
if os.path.exists(city_db):
    db_files.append((city_db, 'for_ip/i18n_security/data'))

datas = numba_datas + llvmlite_datas + cv2_datas + ffmpeg_datas + db_files
binaries = vc_binaries + numba_binaries + llvmlite_binaries + cv2_binaries + ffmpeg_binaries
hiddenimports = ['pee_stego', 'pyinstaller_utils', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets'] + numba_hiddenimports + llvmlite_hiddenimports + cv2_hiddenimports + ffmpeg_hiddenimports

a = Analysis(
    ['src/player_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='StegoPlayer',
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
