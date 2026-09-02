# Nishizumi Translations

Turn Japanese audio and video into transcripts and subtitle files. Drop a file in, pick a model, get `srt`/`vtt`/`ass` out — optionally translated into another language — then attach, embed or burn the result into your video.

**There is nothing to install by hand.** The app downloads and installs its own Whisper models, its own FFmpeg, and (optionally) the NVIDIA GPU libraries. You choose what you want — and which drive it all goes on — from the **Components** page, and it handles the rest.

> The Python package and command line tool are still called `jp2subs`.

## Experimental sibling: Nishizumi Reuniões

An experimental build in this repository transcribes **meeting recordings in
Brazilian Portuguese** into a plain text transcript — speech times, what was
said, and who said it. It only transcribes: no translation, no subtitle
burning, no editing.

It downloads its own models and FFmpeg the same way this app does, and shares
the same component folder, so nothing is downloaded twice.

See **[docs/REUNIOES.md](docs/REUNIOES.md)** for how to install and use it. It
is published as a hidden pre-release, separately from the releases below.

## Install

### Windows (recommended)

Download `Nishizumi-Translations-Setup-<version>.exe` from the [latest release](https://github.com/nishizumi-maho/Nishizumi-Translations/releases/latest) and run it.

- Installs per user, so there is no admin prompt.
- Setup asks for two folders: the program itself, and where the models are downloaded. Point the second one at a roomier drive if the system disk is tight.
- On first launch a short setup screen offers FFmpeg and a speech model, and lets you change the model folder again before anything downloads.
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
6. Optionally tick **Translate after transcribing** and choose target languages — see [Translation](#translation).
7. Click **Start transcription**. The stage timeline shows only the stages this run will use (Ingest → Transcribe → Romanize → Translate → Export) with live progress, and **Cancel** stops the queue including any running FFmpeg process.

### Finalize

Takes a video plus an existing subtitle file and produces one of:

- **Sidecar file** — copies the subtitle next to the video with a matching name. Instant.
- **Soft-mux** — embeds it as a selectable track (MKV takes ASS or SRT, MP4 takes SRT or VTT). No re-encode.
- **Burn in** — renders it permanently into the picture, with controls for font, size, colour (via a colour picker), outline, shadow, background box, position and margin, plus codec/CRF/preset.

### Components

Everything downloadable, with its size, what it is for, and whether it is installed:

**General purpose**

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

**Tuned for Japanese** — these usually beat a general model of the same size on Japanese audio.

| Model | Download | Notes |
| --- | --- | --- |
| Kotoba Whisper v2.0 | ~1.4 GB | Distilled for Japanese. Faster than Large v3 and often more accurate on it. Japanese only. |
| Kotoba Whisper Bilingual v1.0 | ~1.4 GB | Japanese and English, including direct Japanese-to-English speech translation. |
| Whisper Large v2 (Japanese tuned) | ~2.9 GB | Large v2 with 5k extra steps of Japanese. Heavy, strong on hard audio. |

Large v3 Turbo is the recommended starting point. Distil Large v3 is tuned for English, so it trails the others on Japanese.

#### Find any other model

The curated list is a starting point, not a limit. The **Find another model** box searches Hugging Face directly, so a Whisper release that appears after this app was built is one search away — no update needed.

Anything published in CTranslate2 format works. The search only lists repositories that actually have `model.bin` and `config.json`, so nothing you can install will fail to load. You can also paste a repository id or a full `huggingface.co` URL. Models installed this way show up in the model picker next to the built-in ones and can be removed the same way.

Also here:

- **FFmpeg** (~163 MB, required) — a static build, trimmed to `ffmpeg` and `ffprobe`.
- **NLLB-200 offline translator** (~1.2 GB, optional) — translates subtitles into ~200 languages locally. See [Translation](#translation).
- **NVIDIA GPU acceleration** (~1.2 GB, optional, Windows x64) — the cuBLAS and cuDNN libraries that let transcription run on an NVIDIA card. Transcription works on CPU without it.

Downloads resume if interrupted, can be cancelled, and are checked for free disk space first. **Remove** deletes a component again.

Everything lands in a single folder, which by default is:

- Windows: `%LOCALAPPDATA%\jp2subs`
- macOS: `~/Library/Application Support/jp2subs`
- Linux: `$XDG_DATA_HOME/jp2subs` or `~/.local/share/jp2subs`

#### Installing on another drive

Models run from a few hundred megabytes to several gigabytes, so the folder does not have to be on the system disk. Change it from **Components → Change location**, from **Settings → Install location**, or during Windows setup.

Pick any folder on any drive — `D:\jp2subs`, an external disk, a NAS mount. The app offers to carry everything already downloaded across, so installed models keep working without being downloaded again; it warns first if the destination is short on space. Choosing a folder that already holds other files is declined, so removing a component can never delete anything of yours.

The choice is recorded in `data_location.json` next to `config.toml`, and applies to models, FFmpeg, the GPU libraries and the update cache alike. `JP2SUBS_DATA_DIR` still overrides everything, which is handy for a portable install on a USB stick.

### Settings

Theme (dark or light, applied immediately), update preferences, translation engine keys, an optional FFmpeg path override, the install location for downloaded components, and the defaults used for every new run. Saved to:

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
jp2subs setup --data-dir D:\\jp2subs    # install everything on another drive
jp2subs components list                # what is installed, and what it costs
jp2subs components search "whisper japanese"
jp2subs components install large-v3
jp2subs components install kotoba-tech/kotoba-whisper-v2.0-faster
jp2subs components install translator  # the offline translation model
jp2subs components remove tiny
jp2subs components path                # where downloads live
jp2subs components location            # that folder, plus space used and free
jp2subs components location D:\\jp2subs # move everything to another drive
jp2subs components location --default  # back to the standard per-user folder
jp2subs deps doctor                    # check the whole setup
```

`install` and `remove` accept `ffmpeg`, `cuda`, `translator`, a model name like `large-v3-turbo`, a full key like `model:large-v3-turbo`, or any Hugging Face `owner/model` id.

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

# 3b) Translate (optional)
jp2subs translate workdir/master.json --to en,pt-BR

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

Tick **Translate after transcribing** on the Transcribe page, pick your languages, and each run writes `subs_ja.srt` plus one file per language. Tick the bilingual option as well and you also get `subs_en_bilingual.srt` with the translation on top and the Japanese underneath.

Three engines are available, and you choose per run:

| Engine | Needs | Privacy | Best at |
| --- | --- | --- | --- |
| **Offline (NLLB-200)** | A ~1.2 GB download | Nothing leaves the machine | Ordinary dialogue, ~200 languages, free forever |
| **DeepL** | A DeepL API key | Text goes to DeepL | Natural everyday phrasing |
| **OpenAI-compatible** | An endpoint, usually a key | Text goes to that endpoint | Names, honorifics and slang |

The offline engine needs no extra Python packages: it runs on the CTranslate2 runtime already bundled for speech recognition. It is genuinely good on plain sentences, and genuinely weak on proper nouns — 黒森峰女学園 comes out as "Nursing Peak Girls' School". If character names matter to you, use the OpenAI-compatible engine.

"OpenAI-compatible" means any server speaking the `/chat/completions` API — OpenAI, OpenRouter, or a local LM Studio or Ollama instance, which keeps things private *and* handles names well. Set the endpoint in **Settings → Translation engines**; leave the key empty for a local server.

Keys are stored in plain text in your local `config.toml`, the same as every other setting.

Translating from the command line:

```bash
jp2subs translate workdir/master.json --to en,pt-BR
jp2subs translate workdir/master.json --to es --engine openai --bilingual
jp2subs translate x --list-languages
```

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

The same workflow can be started by hand from the **Actions** tab — give it a tag such as `v2.3.0` and the branch to cut it from (`main` by default). It builds an existing tag as-is, and creates the tag itself when there is none yet, after the version check passes. That is the route to use when you cannot push a tag from where you are working.

The app icon is generated from the logo the UI draws:

```bash
python assets/generate_icon.py
```

## Repository layout

- `src/jp2subs/` — CLI, pipeline, ASR, subtitles, FFmpeg helpers
- `src/jp2subs/runtime/` — the self-install layer: catalog, search, downloader, component manager, storage location, updater
- `src/jp2subs/translation/` — language registry and the offline/DeepL/OpenAI engines
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
