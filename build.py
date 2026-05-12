#!/usr/bin/env python3
"""
Build script — generates a standalone executable for the current platform.

  Windows  →  dist\AIFF_Converter\AIFF_Converter.exe
  macOS    →  dist/AIFF_Converter.app
  Linux    →  dist/AIFF_Converter/AIFF_Converter

Run once before building:
  pip install -r requirements.txt
"""
import subprocess
import sys
import platform
import shutil
from pathlib import Path

NAME   = 'AIFF_Converter'
SCRIPT = 'audio_converter.py'

# Clean previous build
for d in ('build', 'dist', f'{NAME}.spec'):
    p = Path(d)
    if p.exists():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        print(f'Removed {d}')

cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--name', NAME,
    '--windowed',       # no console window
    '--onefile',        # single executable, extracts to temp on launch
    '--noconfirm',
    '--collect-all', 'imageio_ffmpeg',
    '--collect-all', 'mutagen',
    # mutagen uses dynamic imports per format — list them explicitly so
    # PyInstaller includes them even if static analysis misses them
    '--hidden-import', 'mutagen.flac',
    '--hidden-import', 'mutagen.mp3',
    '--hidden-import', 'mutagen.mp4',
    '--hidden-import', 'mutagen.aiff',
    '--hidden-import', 'mutagen.ogg',
    '--hidden-import', 'mutagen.oggvorbis',
    '--hidden-import', 'mutagen.oggopus',
    '--hidden-import', 'mutagen.wavpack',
    '--hidden-import', 'mutagen.asf',
    '--hidden-import', 'mutagen.id3',
    '--hidden-import', 'mutagen.id3._frames',
    '--hidden-import', 'mutagen.id3._specs',
    '--hidden-import', 'mutagen.id3._tags',
    '--hidden-import', 'mutagen._util',
    '--hidden-import', 'mutagen._tags',
    SCRIPT,
]

# Include tkinterdnd2 only if it is actually installed
try:
    import tkinterdnd2  # noqa: F401
    cmd += ['--collect-all', 'tkinterdnd2']
    print('tkinterdnd2 found — drag & drop will work inside the window')
except ImportError:
    print('tkinterdnd2 not found — using file picker + drag-onto-exe instead')

print(f'\nBuilding for {platform.system()} ({platform.machine()})...\n')
result = subprocess.run(cmd, check=False)

if result.returncode == 0:
    dist = Path('dist') / NAME
    print('\nBuild successful!')
    if platform.system() == 'Darwin':
        print(f'  App: dist/{NAME}.app')
    elif platform.system() == 'Windows':
        print(f'  Executable: dist/{NAME}.exe')
        print(f'  Tip: you can drag audio files directly onto the .exe to load them automatically')
    else:
        print(f'  Executable: dist/{NAME}')
else:
    print('\nBuild failed. Check the output above.')
    sys.exit(1)
