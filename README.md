# Nishizumi Translations

![unnamed](https://github.com/user-attachments/assets/210bd1f7-f8b0-4cba-aa75-e89a92796484)

Turn Japanese audio and video into transcripts and subtitle files. Drop a file in, pick a model, get `srt`/`vtt`/`ass` out — then attach, embed or burn the result into your video.

**There is nothing to install by hand.** The app downloads and installs its own Whisper models, its own FFmpeg, and (optionally) the NVIDIA GPU libraries. You choose what you want from the **Components** page and it handles the rest.

> The Python package and command line tool are still called `jp2subs`.

## Install

### Windows (recommended)

Download `Nishizumi-Translations-Setup-<version>.exe` from the [latest release](https://github.com/nishizumi-maho/Nishizumi-Translations/releases/latest) and run it.

- Installs per user, so there is no admin prompt.
- On first launch a short setup screen offers FFmpeg and a speech model.
- The app checks for new versions on startup and can update itself from the **About** page.

### From source (any platform)

```bash
git clone https://github.com/nishizumi-maho/Nishizumi-Translations.git
cd Nishizumi-Translations
python -m venv .venv
```

Activate it — Windows `\.venv\Scripts\activate`, macOS/Linux `source .venv/bin/activate` — then:

```bash
pip install -e ".[gui,asr]"
jp2subs setup
jp2subs ui
```

`jp2subs setup` downloads FFmpeg and the recommended model. Requires Python 3.11+.

## Using the app

The window has five sections down the left side.

### Transcribe

1. Drop audio or video onto the panel, or click **Choose files**. Queue as many as you like.
2. Pick a **Model**. Only installed models are listed; **Download another model…** jumps to Components.
3. Choose the subtitle format, and tick **Romaji** if you want a romaji track alongside the Japanese one.
4. Leave **Output folder** blank to get a `_jobs/<filename>` folder next to each input. With several files queued and a folder chosen, each file gets its own subfolder.
5. **Advanced settings** holds the processing device, beam size, voice detection, CPU threads, compute type and raw faster-whisper arguments.
6. Click **Start transcription**. The stage timeline shows Ingest → Transcribe → Romanize → Export with live progress, and **Cancel** stops the queue including any running FFmpeg process.

### Finalize

Takes a video plus an existing subtitle file and produces one of:

- **Sidecar file** — copies the subtitle next to the video with a matching name. Instant.
- **Soft-mux** — embeds it as a selectable track (MKV takes ASS or SRT, MP4 takes SRT or VTT). No re-encode.
- **Burn in** — renders it permanently into the picture, with controls for font, size, colour (via a colour picker), outline, shadow, background box, position and margin, plus codec/CRF/preset.

### Components

Everything downloadable, with its size, what it is for, and whether it is installed:

| Model | Download | Quality | Speed |
| --- | --- | --- | --- |
| Whisper Tiny | ~75 MB | Basic | Fastest |
| Whisper Base | ~141 MB | Basic | Very fast |
| Whisper Small | ~464 MB | Good | Fast |
| Whisper Medium | ~1.4 GB | Very good | Moderate |
| **Whisper Large v3 Turbo** | ~1.5 GB | Excellent | Fast |
| Distil Whisper Large v3 | ~1.4 GB | Good | Fast |
| Whisper Large v2 | ~2.9 GB | Excellent | Slow |
| Whisper Large v3 | ~2.9 GB | Best | Slow |

Large v3 Turbo is the recommended starting point: close to Large v3 accuracy at a fraction of the runtime. Distil Large v3 is tuned for English, so it trails the others on Japanese.

Also here:

- **FFmpeg** (~163 MB, required) — a static build, trimmed to `ffmpeg` and `ffprobe`.
- **NVIDIA GPU acceleration** (~1.2 GB, optional, Windows x64) — the cuBLAS and cuDNN libraries that let transcription run on an NVIDIA card. Transcription works on CPU without it.

Downloads resume if interrupted, can be cancelled, and are checked for free disk space first. **Remove** deletes a component again.

Everything lands in a single folder:

- Windows: `%LOCALAPPDATA%\jp2subs`
- macOS: `~/Library/Application Support/jp2subs`
- Linux: `$XDG_DATA_HOME/jp2subs` or `~/.local/share/jp2subs`

Set `JP2SUBS_DATA_DIR` to put it somewhere else.

### Settings

Theme (dark or light, applied immediately), update preferences, an optional FFmpeg path override, and the defaults used for every new run. Saved to:

- Windows: `%APPDATA%\jp2subs\config.toml`
- other: `~/.config/jp2subs/config.toml`

### About

Version, project links, and the update flow: check, download, install. The installer replaces the running copy and needs no admin rights.

## Command line

The GUI is one command away — `jp2subs ui` — but everything is scriptable.

### Setup and components

```bash
jp2subs setup                          # ffmpeg + the recommended model
jp2subs setup --model small --gpu      # a specific model, plus the CUDA libraries
jp2subs components list                # what is installed, and what it costs
jp2subs components install large-v3
jp2subs components remove tiny
jp2subs components path                # where downloads live
jp2subs deps doctor                    # check the whole setup
```

`install` and `remove` accept `ffmpeg`, `cuda`, a model name like `large-v3-turbo`, or a full key like `model:large-v3-turbo`.

### Updates

```bash
jp2subs update            # is there a newer release?
jp2subs update --install  # download it and start the installer
jp2subs --version
```

### Pipeline

```bash
# 1) Extract audio into a workdir
jp2subs ingest input.mkv --workdir workdir

# 2) Transcribe to master.json
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3-turbo

# 3) Add romaji (optional)
jp2subs romanize workdir/master.json --workdir workdir

# 4) Export subtitles
jp2subs export workdir/master.json --fmt ass --lang ja --out workdir/subs_ja.ass

# 5) Deliver
jp2subs sidecar  input.mkv workdir/subs_ja.ass --out-dir releases
jp2subs softcode input.mkv workdir/subs_ja.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_ja.ass --same-name --suffix .hard --crf 18
```

`--model-size` takes a catalog name (`tiny`, `small`, `medium`, `large-v2`, `large-v3`, `large-v3-turbo`, `distil-large-v3`) or a path to your own CTranslate2 folder. Installed models resolve to a local folder, so transcription runs offline.

### Batch and wizards

```bash
jp2subs batch <input_dir> --ext "mp4,mkv,flac" --workdir workdir --fmt srt
jp2subs wizard     # guided single-file run
jp2subs finalize   # guided mux/burn/sidecar
```

## GPU acceleration

Install **NVIDIA GPU acceleration** from Components, leave the device on **Automatic**, and transcription uses the GPU when one is present, falling back to CPU otherwise. The app adds the downloaded cuBLAS/cuDNN folder to its own library search path — nothing is installed system-wide and `PATH` is left alone.

Selecting a GPU-only compute type (`float16`) while running on CPU is silently downgraded to `int8` rather than failing.

## Translation

Built-in translation is not part of the workflow. The app produces clean Japanese transcripts and subtitles; translate those with your own tooling.

## Building

```powershell
python build_executable.py --mode onedir --clean
```

Produces `dist/NishizumiTranslations/`. To build the Windows installer you also need [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```powershell
iscc /DMyAppVersion=2.1.0 installer\jp2subs.iss
```

Which writes `dist/installer/Nishizumi-Translations-Setup-2.1.0.exe`.

Releases are automated: pushing a `v*` tag runs [`.github/workflows/release.yml`](.github/workflows/release.yml), which builds the bundle, compiles the installer, and attaches it plus a SHA-256 checksum to the GitHub release. The workflow fails if the tag does not match `jp2subs.__version__`.

The app icon is generated from the logo the UI draws:

```bash
python assets/generate_icon.py
```

## Repository layout

- `src/jp2subs/` — CLI, pipeline, ASR, subtitles, FFmpeg helpers
- `src/jp2subs/runtime/` — the self-install layer: catalog, downloader, component manager, updater
- `src/jp2subs/gui/` — theme, shared widgets, and one module per page under `pages/`
- `installer/` — Inno Setup script
- `assets/` — app icon and its generator
- `tests/` — test suite

## Master JSON format

See [`examples/master.sample.json`](examples/master.sample.json).

```json
{
  "meta": { "source": "...", "created_at": "...", "tool_versions": {}, "settings": {} },
  "segments": [
    { "id": 1, "start": 12.34, "end": 15.82, "ja_raw": "...", "romaji": "..." }
  ]
}
```

## Tests

```bash
pip install -e ".[gui,asr]"
pip install pytest
pytest
```

The suite runs offline — no test downloads a model or contacts GitHub.

## License

MIT. See [LICENSE](LICENSE).

Whisper models are the [Systran](https://huggingface.co/Systran) and [Mobius Labs](https://huggingface.co/mobiuslabsgmbh) CTranslate2 conversions. FFmpeg builds come from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds).
