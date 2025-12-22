# jp2subs

jp2subs is a Windows-friendly CLI/GUI tool that turns Japanese audio/video into high-fidelity transcripts and subtitles. The pipeline covers ingestion, ASR (faster-whisper), optional romanization, subtitle export (SRT/VTT/ASS), and mux/burn with ffmpeg. Translation used to be bundled but has been removed because maintaining it in the pipeline is too complex. Use a local LLM, DeepL, or a chatbot like ChatGPT to translate the generated transcripts if needed.

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

## Installation
Requirements: Python 3.11+, ffmpeg on PATH (Windows). Optional: `faster-whisper` for ASR, `requests` for generic API providers.

```bash
python -m venv .venv
.venv\\Scripts\\activate  # PowerShell
pip install -e .
# Extras
pip install jp2subs[asr]     # faster-whisper
pip install jp2subs[llm]     # requests for generic API
pip install jp2subs[gui]     # PySide6 for the desktop interface
```

Models:
- **faster-whisper**: download a model (e.g., `large-v3`) and keep it in the default cache (~AppData/Local/whisper).

## Quickstart
```bash
# GUI
jp2subs ui

# 1) Ingest (extract audio to workdir)
jp2subs ingest input.mkv --workdir workdir

# 2) Transcribe
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3

# 3) Romanize (optional)
jp2subs romanize workdir/master.json --workdir workdir

# 4) Export Japanese subtitles
jp2subs export workdir/master.json --format ass --lang ja --out workdir/subs_ja.ass

# 5) Apply subtitles (soft-mux, hard-burn, or sidecar)
jp2subs softcode input.mkv workdir/subs_ja.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_ja.ass --same-name --suffix .hard --crf 18
jp2subs sidecar input.mkv workdir/subs_ja.ass --out-dir releases

# Need another language? Translate the generated transcript with a local LLM, DeepL, or ChatGPT, then remux using hardcode/softcode/sidecar.
```

Tip: jp2subs now always outputs Japanese transcripts/subtitles; use those files with an external translator if you need another language.

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
