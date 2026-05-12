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
    '--onedir',         # folder build — faster startup, avoids DLL path issues
    '--noconfirm',
    '--collect-all', 'imageio_ffmpeg',
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
    print(f'\n✓ Build successful!')
    if platform.system() == 'Darwin':
        print(f'  App: dist/{NAME}.app')
    elif platform.system() == 'Windows':
        print(f'  Executable: {dist / (NAME + ".exe")}')
        print(f'  Tip: you can drag audio files directly onto the .exe to load them automatically')
    else:
        print(f'  Executable: {dist / NAME}')
    print(f'\nDistribute the entire  dist/{NAME}/  folder — do not move just the exe.')
else:
    print('\n✗ Build failed. Check the output above.')
    sys.exit(1)
