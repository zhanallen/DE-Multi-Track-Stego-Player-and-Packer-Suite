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

datas = numba_datas + llvmlite_datas + cv2_datas + ffmpeg_datas
binaries = vc_binaries + numba_binaries + llvmlite_binaries + cv2_binaries + ffmpeg_binaries
hiddenimports = ['stego_facade', 'audio_chunker', 'pee_stego', 'pyinstaller_utils'] + numba_hiddenimports + llvmlite_hiddenimports + cv2_hiddenimports + ffmpeg_hiddenimports

a = Analysis(
    ['src/embed_app.py'],
    pathex=['src'],
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
    name='StegoPacker',
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
