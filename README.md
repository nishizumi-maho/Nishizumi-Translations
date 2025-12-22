# jp2subs

jp2subs is a Windows-friendly CLI/GUI tool that turns Japanese audio/video into high-fidelity multi-language subtitles. The pipeline covers ingestion, ASR (faster-whisper), romanization, LLM translation (or draft + post-edit), subtitle export (SRT/VTT/ASS), and mux/burn with ffmpeg.

## Key features
- Accepts videos (mp4/mkv/webm/etc.) and audio files (flac/mp3/wav/m4a/mka).
- Extracts audio with ffmpeg (FLAC 48 kHz, stereo/mono configurable).
- Transcription via `faster-whisper` (temperature=0, optional VAD, word timestamps when available).
- Master JSON with segments `{id, start, end, ja_raw, romaji, translations{...}}`.
- Romanization with `pykakasi`.
- Pluggable translation: `llm` mode (local `llama.cpp` or generic API) and `draft+postedit` (NLLB draft + LLM post-edit).
- Exports SRT/VTT/ASS, supports bilingual output (e.g., JP + EN). Line breaks at ~42 characters and max 2 lines.
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
- **llama.cpp**: run `jp2subs deps install-llama` (or `jp2subs install-llama`) to download the latest release to
  `%APPDATA%\\jp2subs\\deps\\llama.cpp\\<tag>` and set `translation.llama_binary` in `%APPDATA%\\jp2subs\\config.toml`.
  Point `translation.llama_model` (or `JP2SUBS_LLAMA_MODEL`) to your `model.gguf` file. Run `jp2subs deps install-model`
  to download a recommended GGUF to `%APPDATA%\\jp2subs\\models` and update the config automatically.
- **NLLB** (optional draft): use your preferred offline runner (hook provider manually or pre-process).

## Quickstart
```bash
# GUI
jp2subs ui

# 1) Ingest (extract audio to workdir)
jp2subs ingest input.mkv --workdir workdir

# 2) Transcribe
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3

# 3) Romanize
jp2subs romanize workdir/master.json --workdir workdir

# 4) Translate (e.g., English, provider via llama.cpp)
jp2subs translate workdir/master.json --to en --mode llm --provider local --block-size 20

# 5) Export bilingual subtitles (JP + EN)
jp2subs export workdir/master.json --format ass --lang en --bilingual ja --out workdir/subs_en.ass

# 6) Apply subtitles (soft-mux, hard-burn, or sidecar)
jp2subs softcode input.mkv workdir/subs_en.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_en.ass --same-name --suffix .hard --crf 18
jp2subs sidecar input.mkv workdir/subs_en.ass --out-dir releases
```

Tip: leave the translation language field blank in the GUI/wizard to produce Japanese-only transcripts and subtitles without running translation.

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
    {"id": 1, "start": 12.34, "end": 15.82, "ja_raw": "...", "romaji": "...", "translations": {"en": "..."}}
  ]
}
```

## Built-in prompts (quality and fidelity)
- **Minimal normalization (optional)**: keep tics, no rewrites.
- **Faithful-natural translation (blocks)**: prioritize fidelity, avoid inventing content, keep interjections and honorifics; one output per line.
- **Post-edit (draft+postedit)**: refine a draft translation while preserving intent and vocal tics.
Full texts live in `src/jp2subs/translation.py`.

## Translation quality guidelines
- Fidelity first: avoid inventing or trimming filler (えっと, あの, うん, etc.).
- Preserve repetitions/hesitations, proper names, and honorifics unless a glossary overrides them.
- Optional glossary via JSON (`--glossary`), applied by the provider.

## Repository structure
- `src/jp2subs/`: source code (CLI, ASR wrapper, romanization, translation, exporters, ffmpeg helpers)
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
- Integrate NLLB directly (onnx/ct2) for draft.
- Add ASS style presets tuned for anime.
- Optional richer UI.

## License
MIT (see [LICENSE](LICENSE)).
