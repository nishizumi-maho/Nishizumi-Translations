# Nishizumi-Translations - jp2subs

![unnamed](https://github.com/user-attachments/assets/210bd1f7-f8b0-4cba-aa75-e89a92796484)

`jp2subs` is a Windows-friendly CLI/GUI tool that turns Japanese audio or video into transcripts and subtitle files. The current project focuses on ingestion, ASR with `faster-whisper`, optional romaji generation, subtitle export, and final video delivery with `ffmpeg`.

Built-in translation is no longer part of the main workflow. The app now produces Japanese transcripts/subtitles cleanly, and you can translate those outputs with your own local LLM, DeepL, or ChatGPT workflow if needed.

## Highlights
- Accepts common video formats (`mp4`, `mkv`, `webm`, `mov`, `avi`) and audio formats (`flac`, `mp3`, `wav`, `m4a`, `mka`).
- Extracts audio with `ffmpeg` to FLAC 48 kHz.
- Transcribes Japanese audio with `faster-whisper`.
- Optionally adds romaji with `pykakasi`.
- Exports subtitles as `srt`, `vtt`, or `ass`.
- Finalizes outputs as sidecar subtitles, soft-muxed video, or hard-burned video.
- GUI supports drag and drop, multi-file queues, stage progress, cancellation, and advanced ASR overrides.
- Saved `ffmpeg_path` in the Settings tab is used by both `ffmpeg` and `ffprobe`.

## Requirements
- Python 3.11+
- `ffmpeg`
- Optional but recommended for the full app:
  - `PySide6` for the GUI
  - `faster-whisper` for transcription

`ffmpeg` can be on your `PATH`, or you can point the GUI to it later in the **Settings** tab.

## Installation
### 1) Clone the repository
```bash
git clone https://github.com/nishizumi-maho/Nishizumi-Translations.git
cd Nishizumi-Translations
```

### 2) Create a virtual environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install the project
For the standard GUI + ASR workflow:
```bash
pip install -e ".[gui,asr]"
```

If you only want the CLI without the GUI:
```bash
pip install -e ".[asr]"
```

### 4) Check ffmpeg
```bash
ffmpeg -version
```

If the command is not found:
- Windows: install `ffmpeg` and add its `bin` folder to `PATH`
- macOS: `brew install ffmpeg`
- Linux: use your package manager, for example `sudo apt install ffmpeg`

## Launching the app
```bash
# Desktop GUI
jp2subs ui

# Interactive CLI wizard
jp2subs wizard
```

## GUI workflow
### Pipeline tab
1. Launch `jp2subs ui`.
2. Drop one or more files into the **Input queue**, or click **Choose files**.
3. Leave **Workdir** blank to use the automatic `_jobs/<file-stem>` folder next to the input.
4. If you choose a custom workdir and queue multiple files, the app creates one subfolder per source file to avoid output collisions.
5. Adjust the pipeline options you want:
   - model
   - beam size
   - VAD
   - mono/stereo ingest
   - subtitle format
   - romaji generation
   - word timestamps
   - CPU threads
   - compute type
   - extra ASR args
6. Click **Run**.
7. Watch the stage list and log panel while ingest, transcription, romaji, and export run.
8. If needed, click **Cancel queue**. The GUI now propagates cancellation to the running pipeline and active `ffmpeg` subprocesses where possible.

### Finalize tab
Use the **Finalize** tab when you already have a subtitle file and want to:
- create a sidecar subtitle
- soft-mux subtitles into a video container
- hard-burn subtitles into a new video

The finalize screen also exposes subtitle styling controls for burn-in, including:
- font
- size
- bold/italic
- outline/shadow
- alignment
- margin
- primary/background color

### Settings tab
Use **Settings** to manage default behavior:
- `ffmpeg_path`
- default model size
- beam size
- VAD
- mono ingest
- subtitle format
- advanced ASR defaults such as:
  - best-of
  - patience
  - length penalty
  - word timestamps
  - threads
  - compute type
  - suppress blank
  - suppress tokens
  - extra ASR args

Settings are saved to:
- Windows: `%APPDATA%/jp2subs/config.toml`
- non-Windows: `~/.config/jp2subs/config.toml`

The **Detect ffmpeg** button helps fill the path field, and the saved `ffmpeg_path` is also used to locate the matching `ffprobe`.

## CLI quickstart
```bash
# 1) Ingest media into a workdir
jp2subs ingest input.mkv --workdir workdir

# 2) Transcribe audio/video and generate master.json
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3

# 3) Add romaji (optional)
jp2subs romanize workdir/master.json --workdir workdir

# 4) Export Japanese subtitles
jp2subs export workdir/master.json --format ass --lang ja --out workdir/subs_ja.ass

# 5) Finalize subtitles for playback/distribution
jp2subs softcode input.mkv workdir/subs_ja.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_ja.ass --same-name --suffix .hard --crf 18
jp2subs sidecar input.mkv workdir/subs_ja.ass --out-dir releases
```

If you want to use a local converted Whisper model instead of a built-in model name, pass the local model path, for example:

```text
C:\model\whisper-jp-ct2
```

## Manual CLI usage
### Ingest
```bash
jp2subs ingest <input> --workdir <folder> [--mono]
```

### Transcribe
```bash
jp2subs transcribe <input> --workdir <folder> --model-size large-v3 --device auto --vad --temperature 0 --beam-size 5
```

Key options:
- `--model-size`: `tiny`, `small`, `medium`, `large-v3`, or a local CTranslate2 model path
- `--device`: `auto`, `cuda`, or `cpu`
- `--vad / --no-vad`
- `--temperature`
- `--beam-size`

### Romanize
```bash
jp2subs romanize <workdir>/master.json --workdir <folder>
```

### Export
```bash
jp2subs export <workdir>/master.json --format ass --lang ja --out <path> --workdir <folder>
```

### Final subtitle delivery
**Soft-mux**
```bash
jp2subs softcode <video> <subs> --container mkv --same-name --lang ja
```

**Hard-burn**
```bash
jp2subs hardcode <video> <subs> --same-name --suffix .hard --crf 18 --codec libx264 --preset slow
```

**Sidecar**
```bash
jp2subs sidecar <video> <subs> --out-dir <folder> --same-name
```

## Batch processing
You can process many files from a folder with the CLI:

```bash
jp2subs batch <input_dir> --ext "mp4,mkv,flac" --workdir workdir --model-size large-v3 --format srt
```

Useful flags:
- `--ext`: comma-separated extensions
- `--force`: re-run stages even if cache markers already exist
- `--mono`: downmix during ingest

## Finalize existing subtitles interactively
```bash
jp2subs finalize
```

This opens the CLI finalize wizard for:
- sidecar
- softcode
- hardcode

## Build a Windows executable
The repository includes a PyInstaller helper script for building the GUI as a Windows app.

```powershell
python build_executable.py --mode onedir --clean
```

Output:
- `dist/jp2subs-gui/`

Notes:
- `onedir` is the recommended mode for the current project.
- Install the dependencies you want bundled before building, especially `.[gui,asr]`.
- The generated `dist/` and `build/` folders are ignored by Git.

## Master JSON format
See [`examples/master.sample.json`](examples/master.sample.json).

Example:
```json
{
  "meta": {
    "source": "...",
    "created_at": "...",
    "tool_versions": {},
    "settings": {}
  },
  "segments": [
    {
      "id": 1,
      "start": 12.34,
      "end": 15.82,
      "ja_raw": "...",
      "romaji": "..."
    }
  ]
}
```

## Repository structure
- `src/jp2subs/`: CLI, GUI, ASR helpers, romanization, exporters, ffmpeg helpers
- `examples/`: sample `master.json`
- `tests/`: automated tests
- `build_executable.py`: PyInstaller helper for the Windows GUI build
- `.github/workflows/`: CI/build automation

## Running tests
```bash
pip install -e ".[gui,asr]"
pip install pytest
pytest
```

## License
MIT. See [LICENSE](LICENSE).
