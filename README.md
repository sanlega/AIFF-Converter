# AIFF Converter

Batch convert audio files to **AIFF 16-bit 44.1 kHz PCM** — the format required by Beatport, Traxsource, and most digital distribution platforms.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)

## Download

Grab the latest build from the [Releases](https://github.com/sanlega/AIFF-Converter/releases) page:

- **Windows** → `AIFF_Converter_Windows.zip` — extract and run `AIFF_Converter.exe`
- **Linux** → `AIFF_Converter_Linux.tar.gz` — extract and run `AIFF_Converter`
- **macOS** → build from source (see below)

## Usage

1. Open the app
2. Click the blue zone to pick files, or drag files onto it
3. Hit **Convert**
4. Converted files appear in a `converted/` folder next to the originals

> **Windows tip:** you can also drag audio files directly onto `AIFF_Converter.exe` — they'll load automatically when the app opens.

## Supported input formats

FLAC, WAV, MP3, AAC, M4A, OGG, OPUS, WMA, APE, WV, CAF, ALAC, AIF, AIFF and more.

## Output

| Setting | Value |
|---|---|
| Format | AIFF |
| Bit depth | 16-bit |
| Sample rate | 44,100 Hz |
| Encoding | PCM (uncompressed) |

## Build from source

Requires Python 3.9+ and the dependencies below.

```bash
pip install -r requirements.txt
python build.py
```

The executable will be in `dist/AIFF_Converter/`.

> macOS users: run `build.py` on a Mac to get a native `.app` bundle.
