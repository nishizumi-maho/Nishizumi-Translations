# Nishizumi-Translations

Windows-friendly CLI/GUI tool that turns Japanese audio/video into high-fidelity transcripts and subtitles. The pipeline covers ingestion, ASR (faster-whisper), optional romanization, subtitle export (SRT/VTT/ASS), and mux/burn with ffmpeg. Translation used to be bundled but has been removed because maintaining it in the pipeline is too complex. Use a local LLM, DeepL, or a chatbot like ChatGPT to translate the generated transcripts if needed.

## Key features
- Accepts videos (mp4/mkv/webm/etc.) and audio files (flac/mp3/wav/m4a/mka).
- Extracts audio with ffmpeg (FLAC 48 kHz, stereo/mono configurable).
- Transcription via `faster-whisper` (temperature=0, optional VAD, word timestamps when available).
- Master JSON with segments `{id, start, end, ja_raw, romaji}` for downstream tooling.
- Romanization with `pykakasi`.
- Translation has been removed; bring your own tool (local LLM, DeepL, ChatGPT) if you need another language.
- Exports SRT/VTT/ASS for Japanese transcripts. Line breaks at ~42 characters and max 2 lines.
- Soft-mux to MKV and hard-burn via ffmpeg + libass.
- Workdir caching; pipeline skips stages when `master.json` already exists.

## Installation (step-by-step for first-time users)
Requirements: Python 3.11+, ffmpeg on PATH. Optional: `faster-whisper` for ASR, `requests` for generic API providers, `PySide6` for GUI.

> **Tip:** The CLI works on macOS/Linux/Windows. The GUI requires `jp2subs[gui]`.

### 1) Create a workspace folder
Pick a place where you want the app to live. Example:
```bash
mkdir jp2subs-workspace
cd jp2subs-workspace
```

### 2) Clone the repository
```bash
git clone https://github.com/<your-org-or-user>/Nishizumi-Translations.git
cd Nishizumi-Translations
```

### 3) Create and activate a virtual environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux (bash/zsh):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4) Install the package (editable install)
This lets you run `jp2subs` from the repo:
```bash
pip install -e .
```

### 5) Install optional extras (recommended)
```bash
# ASR (faster-whisper)
pip install jp2subs[asr]

# GUI (desktop app)
pip install jp2subs[gui]

# Generic API helper (requests)
pip install jp2subs[llm]
```

### 6) Install ffmpeg (required for ingest/mux/burn)
Make sure `ffmpeg` is available on your PATH:
```bash
ffmpeg -version
```
If the command is not found, install ffmpeg:
- Windows: download from https://ffmpeg.org/ and add the `bin` folder to PATH.
- macOS: `brew install ffmpeg`
- Linux: use your distro package manager (e.g., `sudo apt install ffmpeg`).

### 7) Download a whisper model (for transcription)
`faster-whisper` uses cached models. The default cache is in `~/.cache/whisper` (Linux/macOS) or `~AppData/Local/whisper` (Windows).
Common choices:
- `small` (fast, lower quality)
- `medium` (balanced)
- `large-v3` (best quality, slower)

### 8) Launch the app
```bash
# GUI
jp2subs ui

# Or just run the CLI wizard
jp2subs wizard
```

## Quickstart (CLI)
```bash
# 1) Ingest (extract audio to workdir)
jp2subs ingest input.mkv --workdir workdir

# 2) Transcribe (generates master.json + transcript_ja.txt + transcript_ja.srt)
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3

# 3) Romanize (optional, adds romaji fields and outputs transcript_romaji.*)
jp2subs romanize workdir/master.json --workdir workdir

# 4) Export Japanese subtitles
jp2subs export workdir/master.json --format ass --lang ja --out workdir/subs_ja.ass

# 5) Apply subtitles (soft-mux, hard-burn, or sidecar)
jp2subs softcode input.mkv workdir/subs_ja.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_ja.ass --same-name --suffix .hard --crf 18
jp2subs sidecar input.mkv workdir/subs_ja.ass --out-dir releases
```

Tip: jp2subs now always outputs Japanese transcripts/subtitles. Use those files with an external translator if you need another language.

## Detailed usage guide
### Option 1: GUI workflow (beginner-friendly)
1. Run `jp2subs ui`.
2. Open the **Pipeline** tab.
3. **Input**: choose your video/audio file.
4. **Workdir**: pick or create a folder where outputs will be saved.
5. Choose **Model size**, **VAD**, **Beam size**, **Device**.
6. Click **Run**. The pipeline shows progress for ingest → transcribe → romanize → export.
7. Use the **Finalize** tab to soft-mux, hard-burn, or create a sidecar subtitle file.

### Option 2: Interactive wizard (CLI)
Run:
```bash
jp2subs wizard
```
The wizard will ask you:
- Input media file
- Workdir
- Mono vs stereo
- Model size (e.g., `small`, `medium`, `large-v3`)
- Beam size (higher = higher quality, slower)
- VAD on/off (on removes silence, off keeps raw timing)
- Device (`auto`, `cuda`, `cpu`)
- Optional romaji
- Subtitle format (`srt`, `vtt`, `ass`)
- Output type (subtitles, mux-soft, burn)

### Option 3: Manual CLI pipeline (advanced)
Use this when you want full control over every step.

#### 1) Ingest
Extracts audio to `<workdir>/audio.flac` (48kHz). If input is already audio, it is copied.
```bash
jp2subs ingest <input> --workdir <folder> [--mono]
```
Options:
- `--workdir`: output folder (default: `workdir`)
- `--mono`: downmix to mono for ASR speed (default: stereo)

#### 2) Transcribe
Creates `<workdir>/master.json`, `<workdir>/transcript_ja.txt`, `<workdir>/transcript_ja.srt`.
```bash
jp2subs transcribe <input> --workdir <folder> --model-size large-v3 --device auto --vad --temperature 0 --beam-size 5
```
Options:
- `--model-size`: whisper model (`tiny`/`small`/`medium`/`large-v3`)
- `--device`: `auto`, `cuda`, or `cpu`
- `--vad / --no-vad`: toggle VAD silence trimming
- `--temperature`: decoding randomness (0 = deterministic)
- `--beam-size`: higher values increase quality/latency

#### 3) Romanize (optional)
Adds `romaji` to `master.json` and writes `transcript_romaji.txt/srt`.
```bash
jp2subs romanize <workdir>/master.json --workdir <folder>
```

#### 4) Export subtitles
```bash
jp2subs export <workdir>/master.json --format ass --lang ja --out <path> --workdir <folder>
```
Options:
- `--format`: `srt`, `vtt`, or `ass`
- `--lang`: language code (default `ja`)
- `--out`: output path (defaults to `<workdir>/subs_<lang>.<format>`)

#### 5) Apply subtitles to a video
**Soft-mux (no re-encode, fastest):**
```bash
jp2subs softcode <video> <subs> --container mkv --same-name --lang ja
```
Options:
- `--container`: `mkv` or `mp4`
- `--same-name`: use video name for output
- `--suffix`: optional suffix for output filename
- `--lang`: subtitle language code tag

**Hard-burn (re-encode, permanent subtitles):**
```bash
jp2subs hardcode <video> <subs> --same-name --suffix .hard --crf 18 --codec libx264 --preset slow
```
Options:
- `--crf`: quality (lower = better, larger file)
- `--codec`: `libx264` or other FFmpeg codec
- `--preset`: encoding speed/quality balance

**Sidecar (external subtitle file):**
```bash
jp2subs sidecar <video> <subs> --out-dir <folder> --same-name
```

### Batch processing
Process many files in a folder:
```bash
jp2subs batch <input_dir> --ext "mp4,mkv,flac" --workdir workdir --model-size large-v3 --format srt
```
Useful flags:
- `--ext`: comma-separated extensions
- `--force`: re-run stages even if cached
- `--mono`: downmix during ingest

### Finalize existing subtitles
If you already have SRT/VTT/ASS files:
```bash
jp2subs finalize
```
You’ll be prompted to select a video, subtitle file, and output mode (sidecar/softcode/hardcode).

### Configure inside the app
- Open the **Settings** tab in the GUI to edit `ffmpeg_path`, default ASR model/beam/vad/mono, and subtitle format.
- Use **Save** to write changes immediately to `%APPDATA%/jp2subs/config.toml` (or `~/.config/jp2subs` on non-Windows). **Load** refreshes from disk and **Reset** restores built-in defaults.
- The **Pipeline** tab exposes advanced ASR overrides (threads, patience, length penalty, compute type, raw extra args) and highlights each stage as it runs.

## Translation
Translation is no longer built into jp2subs. Use an external option such as DeepL, ChatGPT, or a local LLM runner to translate the generated Japanese transcripts before muxing them back with the hardcode/softcode/sidecar commands.

## Build a Windows executable (.exe)
Install PyInstaller and the `gui` extra, then run the PowerShell script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
python -m pip install jp2subs[gui] pyinstaller
pwsh scripts/build_exe.ps1
```

## Screenshots
*(add your captures here; placeholders for catalog)*

## Master JSON format
See [`examples/master.sample.json`](examples/master.sample.json) for the full contract:
```json
{
  "meta": {"source": "...", "created_at": "...", "tool_versions": {...}, "settings": {...}},
  "segments": [
    {"id": 1, "start": 12.34, "end": 15.82, "ja_raw": "...", "romaji": "..."}
  ]
}
```

## Repository structure
- `src/jp2subs/`: source code (CLI, ASR wrapper, romanization, exporters, ffmpeg helpers)
- `examples/`: `master.sample.json` and usage tips
- `configs/`: space for presets (add yours)
- `.github/workflows/ci.yml`: basic lint/tests
- `tests/`: schema and writer unit tests

## Running tests
```bash
pip install -e .
pip install pytest
pytest
```

## Subtitle application modes
- After exporting/editing subtitles, use the dedicated commands to apply them to a video:
  - `jp2subs softcode <video> <subs> --same-name --container mkv` to mux (no re-encode; uses mov_text automatically for MP4).
  - `jp2subs hardcode <video> <subs> --suffix .hard --crf 18` to burn-in with libass, respecting ASS/SRT/VTT.
  - `jp2subs sidecar <video> <subs> --out-dir player\downloads` to copy/rename the subtitle, compatible with players that read external files.

## Suggested roadmap
- Add ASS style presets tuned for anime.
- Optional richer UI.

## License
MIT (see [LICENSE](LICENSE)).
