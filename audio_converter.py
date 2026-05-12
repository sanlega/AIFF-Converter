#!/usr/bin/env python3
import sys
import os
import struct
import tempfile
import threading
import subprocess
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Fix tkinterdnd2 binary path when running as a PyInstaller bundle
if getattr(sys, 'frozen', False):
    _tkdnd = os.path.join(sys._MEIPASS, 'tkinterdnd2', 'tkdnd')
    if os.path.isdir(_tkdnd):
        os.environ.setdefault('TKDND_LIBRARY', _tkdnd)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND = True
except Exception:
    _DND = False


def _find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'


FFMPEG = _find_ffmpeg()


def _parse_ffmeta(text: str) -> dict:
    """Parse ffmetadata format into a lowercase-keyed dict."""
    meta = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('#'):
            continue
        if line.startswith('['):
            break  # stop before chapter/stream sections
        if '=' in line:
            k, _, v = line.partition('=')
            v = v.replace('\\=', '=').replace('\\n', '\n').replace('\\\\', '\\')
            meta[k.strip().lower()] = v.strip()
    return meta


def _syncsafe4(n: int) -> bytes:
    """Encode integer as ID3v2 sync-safe 4-byte big-endian."""
    return bytes([(n >> s) & 0x7F for s in (21, 14, 7, 0)])


def _copy_tags(src: Path, dst: Path):
    """Extract metadata from src using ffmpeg, write ID3v2.3 into dst AIFF.
    Uses only stdlib + ffmpeg — no third-party library needed in the exe.
    """
    try:
        FRAME_MAP = {
            'title':        'TIT2', 'artist':       'TPE1',
            'albumartist':  'TPE2', 'album_artist': 'TPE2',
            'album':        'TALB', 'date':         'TDRC',
            'year':         'TDRC', 'genre':        'TCON',
            'tracknumber':  'TRCK', 'track':        'TRCK',
            'bpm':          'TBPM', 'initialkey':   'TKEY',
            'key':          'TKEY', 'composer':     'TCOM',
        }

        frames = b''
        seen_fids = set()

        with tempfile.TemporaryDirectory() as tmp:

            # ── Text tags via ffmetadata ──────────────────────────────────
            meta_file = os.path.join(tmp, 'meta.txt')
            subprocess.run(
                [FFMPEG, '-i', str(src), '-f', 'ffmetadata', meta_file, '-y'],
                capture_output=True,
            )
            meta = {}
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8', errors='replace') as f:
                    meta = _parse_ffmeta(f.read())

            for mkey, fid in FRAME_MAP.items():
                if fid in seen_fids:
                    continue
                val = meta.get(mkey)
                if val:
                    seen_fids.add(fid)
                    payload = b'\x03' + val.encode('utf-8')   # UTF-8 encoding marker
                    frames += (fid.encode()
                                + struct.pack('>I', len(payload))
                                + b'\x00\x00'
                                + payload)

            # ── Cover art via ffmpeg ──────────────────────────────────────
            cover_file = os.path.join(tmp, 'cover.jpg')
            subprocess.run(
                [FFMPEG, '-i', str(src), '-map', '0:v',
                 '-vcodec', 'copy', '-y', cover_file],
                capture_output=True,
            )
            if os.path.exists(cover_file) and os.path.getsize(cover_file) > 64:
                with open(cover_file, 'rb') as f:
                    cover_bytes = f.read()
                mime = ('image/png'
                        if cover_bytes[:8] == b'\x89PNG\r\n\x1a\n'
                        else 'image/jpeg')
                apic = (b'\x03'                    # UTF-8
                        + mime.encode('ascii')
                        + b'\x00'                  # null-terminate mime
                        + b'\x03'                  # picture type: front cover
                        + b'\x00'                  # empty description
                        + cover_bytes)
                frames += (b'APIC'
                           + struct.pack('>I', len(apic))
                           + b'\x00\x00'
                           + apic)

        if not frames:
            return

        # ── Build ID3v2.3 block ───────────────────────────────────────────
        id3_block = b'ID3\x03\x00\x00' + _syncsafe4(len(frames)) + frames

        # ── Inject ID3 chunk into AIFF file ──────────────────────────────
        with open(str(dst), 'rb') as f:
            raw = f.read()

        if len(raw) < 12 or raw[:4] != b'FORM' or raw[8:12] not in (b'AIFF', b'AIFC'):
            return

        form_type = raw[8:12]
        chunks = b''
        i = 12
        while i + 8 <= len(raw):
            cid   = raw[i:i+4]
            csize = struct.unpack('>I', raw[i+4:i+8])[0]
            if cid != b'ID3 ':                     # drop any pre-existing ID3 chunk
                chunks += raw[i: i + 8 + csize]
                if csize % 2:
                    chunks += b'\x00'              # AIFF word-alignment padding
            i += 8 + csize + (csize % 2)

        # Append new ID3 chunk
        chunks += b'ID3 ' + struct.pack('>I', len(id3_block)) + id3_block
        if len(id3_block) % 2:
            chunks += b'\x00'

        body = form_type + chunks
        with open(str(dst), 'wb') as f:
            f.write(b'FORM' + struct.pack('>I', len(body)) + body)

    except Exception:
        pass  # metadata failure never blocks audio conversion

SUPPORTED = {
    '.flac', '.wav', '.mp3', '.aac', '.m4a', '.ogg', '.opus',
    '.wma', '.aif', '.aiff', '.ape', '.wv', '.caf', '.alac',
    '.mp4', '.mkv', '.mov',
}

FILETYPES = [
    ('Audio', ' '.join(f'*{e}' for e in sorted(SUPPORTED))),
    ('Todos los archivos', '*.*'),
]

BG    = '#1c1c1e'
BG2   = '#2c2c2e'
BG3   = '#3a3a3c'
ACC   = '#0a84ff'
TXT   = '#f2f2f7'
MUTED = '#8e8e93'
GREEN = '#30d158'
RED   = '#ff453a'

F     = ('Helvetica', 11)
F_SM  = ('Helvetica', 9)
F_BIG = ('Helvetica', 14, 'bold')
F_MONO = ('Courier', 10)


if _DND:
    class _Base(TkinterDnD.Tk):
        pass
else:
    class _Base(tk.Tk):
        pass


class Converter(_Base):
    def __init__(self):
        super().__init__()
        self.title('AIFF Converter')
        self.geometry('620x500')
        self.configure(bg=BG)
        self.minsize(440, 360)
        self._files = []
        self._results = {}
        self._build_ui()
        if _DND:
            self.after(200, self._bind_dnd)
        # Files passed as CLI args (drag-onto-.exe on Windows)
        if len(sys.argv) > 1:
            self.after(300, self._load_argv)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=12)
        hdr.pack(fill='x', padx=20)
        tk.Label(hdr, text='AIFF Converter', font=F_BIG, bg=BG, fg=TXT).pack(side='left')
        tk.Label(hdr, text='16-bit · 44.1 kHz · PCM', font=F_SM, bg=BG, fg=MUTED).pack(side='right')

        # Click-to-add zone (also drag target if DnD is available)
        self._zone = tk.Frame(self, bg=BG2, height=76, cursor='hand2')
        self._zone.pack(fill='x', padx=20, pady=(0, 12))
        self._zone.pack_propagate(False)

        self._zone_lbl = tk.Label(
            self._zone,
            text='＋  Seleccionar archivos de audio',
            font=('Helvetica', 12, 'bold'), bg=BG2, fg=ACC, cursor='hand2',
        )
        self._zone_lbl.place(relx=.5, rely=.38, anchor='center')

        if _DND:
            hint = 'o arrastra archivos aquí'
        else:
            hint = 'o arrastra archivos sobre el icono del programa'
        self._zone_hint = tk.Label(
            self._zone, text=hint, font=F_SM, bg=BG2, fg=MUTED, cursor='hand2',
        )
        self._zone_hint.place(relx=.5, rely=.72, anchor='center')

        for w in (self._zone, self._zone_lbl, self._zone_hint):
            w.bind('<Button-1>', lambda e: self._pick_files())
            w.bind('<Enter>', lambda e: self._set_zone_bg(BG3))
            w.bind('<Leave>', lambda e: self._set_zone_bg(BG2))

        # File list
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill='both', expand=True, padx=20)
        sb = ttk.Scrollbar(wrap)
        sb.pack(side='right', fill='y')
        self._lb = tk.Listbox(
            wrap, yscrollcommand=sb.set,
            bg=BG2, fg=TXT, selectbackground=BG3, selectforeground=TXT,
            font=F_MONO, bd=0, highlightthickness=0, activestyle='none',
        )
        self._lb.pack(fill='both', expand=True)
        sb.config(command=self._lb.yview)

        # Footer
        foot = tk.Frame(self, bg=BG, pady=10)
        foot.pack(fill='x', padx=20)
        self._status = tk.Label(foot, text='Listo', font=F_SM, bg=BG, fg=MUTED)
        self._status.pack(side='left')

        tk.Button(
            foot, text='Limpiar', command=self._clear,
            bg=BG3, fg=TXT, relief='flat', padx=12, pady=5,
            cursor='hand2', font=F_SM, activebackground='#4a4a4e',
        ).pack(side='right')

        self._btn_go = tk.Button(
            foot, text='Convertir', command=self._start,
            bg=ACC, fg='white', relief='flat', padx=14, pady=5,
            cursor='hand2', font=('Helvetica', 10, 'bold'),
            activebackground='#0060cc',
        )
        self._btn_go.pack(side='right', padx=(0, 8))

    def _set_zone_bg(self, color):
        self._zone.config(bg=color)
        self._zone_lbl.config(bg=color)
        self._zone_hint.config(bg=color)

    # ── Drag & drop (bonus — only when tkinterdnd2 works) ────────────────────

    def _bind_dnd(self):
        try:
            for w in (self, self._zone, self._zone_lbl, self._zone_hint):
                w.drop_target_register(DND_FILES)
                w.dnd_bind('<<Drop>>', self._on_drop)
        except Exception:
            pass  # DnD unavailable — file picker still works

    @staticmethod
    def _parse_paths(data):
        paths, s = [], data.strip()
        while s:
            if s.startswith('{'):
                end = s.index('}')
                paths.append(s[1:end])
                s = s[end + 1:].strip()
            else:
                part, _, s = s.partition(' ')
                paths.append(part)
                s = s.strip()
        return paths

    def _on_drop(self, event):
        self._add_paths(self._parse_paths(event.data))

    # ── File selection ────────────────────────────────────────────────────────

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title='Seleccionar archivos de audio',
            filetypes=FILETYPES,
        )
        if paths:
            self._add_paths(paths)

    def _load_argv(self):
        self._add_paths(sys.argv[1:])

    def _add_paths(self, raw_paths):
        added = 0
        for raw in raw_paths:
            p = Path(raw)
            if p.is_file() and p.suffix.lower() in SUPPORTED and p not in self._files:
                self._files.append(p)
                self._lb.insert('end', f'  ○  {p.name}')
                self._lb.itemconfig('end', fg=MUTED)
                added += 1
        if added:
            self._refresh_status()

    # ── Conversion ────────────────────────────────────────────────────────────

    def _start(self):
        pending = [p for p in self._files
                   if self._results.get(p) not in ('done', 'converting')]
        if not pending:
            return
        self._btn_go.config(state='disabled', text='Convirtiendo…')
        threading.Thread(target=self._run, args=(pending,), daemon=True).start()

    def _run(self, files):
        for p in files:
            idx = self._files.index(p)
            self._results[p] = 'converting'
            self.after(0, self._set_row, idx, '◌', ACC, p.name)

            out_dir = p.parent / 'converted'
            out_dir.mkdir(exist_ok=True)
            out = out_dir / (p.stem + '.aiff')

            try:
                r = subprocess.run(
                    [FFMPEG, '-i', str(p),
                     '-map', '0:a',           # audio stream only
                     '-acodec', 'pcm_s16be', '-ar', '44100',
                     '-map_metadata', '0',     # copy text tags via ffmpeg
                     '-y', str(out)],
                    capture_output=True,
                    timeout=600,
                )
                ok = r.returncode == 0
                if ok:
                    _copy_tags(p, out)        # cover art + full tag copy via mutagen
                else:
                    self._results[p] = 'error_detail:' + r.stderr.decode('utf-8', errors='replace')[-300:]
            except Exception as exc:
                ok = False
                self._results[p] = f'error_detail:{exc}'

            final = 'done' if ok else 'error'
            if ok:
                self._results[p] = 'done'
            self.after(0, self._set_row, idx,
                       '●' if ok else '✕',
                       GREEN if ok else RED,
                       p.name)
            self.after(0, self._refresh_status)

        self.after(0, lambda: self._btn_go.config(state='normal', text='Convertir'))

    def _set_row(self, i, icon, color, name):
        self._lb.delete(i)
        self._lb.insert(i, f'  {icon}  {name}')
        self._lb.itemconfig(i, fg=color)

    def _refresh_status(self):
        n = len(self._files)
        done  = sum(1 for v in self._results.values() if v == 'done')
        err   = sum(1 for v in self._results.values() if str(v).startswith('error'))
        conv  = sum(1 for v in self._results.values() if v == 'converting')
        if conv:
            self._status.config(text=f'Convirtiendo… {done}/{n}')
        elif self._results:
            parts = [f'{done}/{n} listos']
            if err:
                parts.append(f'{err} error(es)')
            self._status.config(text=' · '.join(parts))
        else:
            self._status.config(text=f'{n} archivo(s) en cola' if n else 'Listo')

    def _clear(self):
        if any(v == 'converting' for v in self._results.values()):
            return
        self._files.clear()
        self._results.clear()
        self._lb.delete(0, 'end')
        self._status.config(text='Listo')


if __name__ == '__main__':
    try:
        app = Converter()
        app.mainloop()
    except Exception:
        # Show error in a dialog instead of silently crashing
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror('Error al iniciar', traceback.format_exc())
        except Exception:
            print(traceback.format_exc())
