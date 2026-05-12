#!/usr/bin/env python3
import sys
import os
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


def _copy_tags(src: Path, dst: Path):
    """Copy all tags + cover art from src to the converted AIFF using mutagen."""
    try:
        from mutagen import File
        from mutagen.aiff import AIFF
        from mutagen.id3 import (
            APIC, TIT2, TPE1, TALB, TDRC, TCON, TRCK, TBPM, TKEY, TCOM, TPE2
        )

        src_file = File(str(src))
        if src_file is None:
            return

        dst_aiff = AIFF(str(dst))
        if dst_aiff.tags is None:
            dst_aiff.add_tags()

        tags = src_file.tags or {}

        # ── Cover art ──────────────────────────────────────────────────────
        artwork_data = artwork_mime = None

        # FLAC / OGG pictures
        if hasattr(src_file, 'pictures') and src_file.pictures:
            pic = src_file.pictures[0]
            artwork_data, artwork_mime = pic.data, pic.mime

        # MP4 / M4A (covr atom)
        elif 'covr' in tags:
            covers = tags['covr']
            if covers:
                artwork_data = bytes(covers[0])
                artwork_mime = 'image/jpeg'

        # ID3-based (MP3, existing AIFF)
        else:
            for key in tags:
                if key.startswith('APIC'):
                    artwork_data = tags[key].data
                    artwork_mime = tags[key].mime
                    break

        if artwork_data:
            dst_aiff.tags['APIC:Cover'] = APIC(
                encoding=3, mime=artwork_mime, type=3,
                desc='Cover', data=artwork_data,
            )

        # ── Text tags (Vorbis Comment → ID3) ──────────────────────────────
        # Covers FLAC, OGG Vorbis, OGG Opus
        if hasattr(src_file, 'pictures') or src_file.mime == ['audio/flac'] \
                or getattr(src_file, '_DictProxy__dict', None) is not None \
                or isinstance(tags, dict):

            def vorbis(key):
                v = tags.get(key) or tags.get(key.upper())
                if isinstance(v, list):
                    v = v[0] if v else None
                return str(v) if v else None

            _vorbis_to_id3 = [
                ('title',        TIT2),
                ('artist',       TPE1),
                ('albumartist',  TPE2),
                ('album',        TALB),
                ('date',         TDRC),
                ('genre',        TCON),
                ('tracknumber',  TRCK),
                ('bpm',          TBPM),
                ('initialkey',   TKEY),
                ('composer',     TCOM),
            ]
            for vkey, frame_cls in _vorbis_to_id3:
                val = vorbis(vkey)
                if val:
                    try:
                        frame = frame_cls(encoding=3, text=val)
                        dst_aiff.tags[frame.HashKey] = frame
                    except Exception:
                        pass

        # ── MP4 atom → ID3 ─────────────────────────────────────────────────
        mp4_map = {
            '\xa9nam': TIT2, '\xa9ART': TPE1, 'aART': TPE2,
            '\xa9alb': TALB, '\xa9day': TDRC, '\xa9gen': TCON,
            'trkn':    TRCK, 'tmpo':  TBPM,
        }
        for atom, frame_cls in mp4_map.items():
            if atom in tags:
                val = tags[atom]
                if isinstance(val, list):
                    val = val[0]
                try:
                    val = str(val[0]) if isinstance(val, tuple) else str(val)
                    frame = frame_cls(encoding=3, text=val)
                    dst_aiff.tags[frame.HashKey] = frame
                except Exception:
                    pass

        dst_aiff.save()

    except Exception:
        pass  # metadata failure never blocks the audio conversion

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
