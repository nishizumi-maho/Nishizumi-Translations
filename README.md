# jp2subs

jp2subs é uma ferramenta CLI pensada para Windows que transforma áudio/vídeo em legendas multilíngues de alta fidelidade para anime e conteúdo japonês. O pipeline cobre ingestão, ASR (faster-whisper), romanização, tradução com LLM ou fluxo draft+postedit, exportação de legendas (SRT/VTT/ASS) e mux/burn com ffmpeg.

## Recursos principais
- Aceita vídeos (mp4/mkv/webm/etc.) e áudios (flac/mp3/wav/m4a/mka).
- Extrai áudio com ffmpeg (FLAC 48 kHz, estéreo/mono configurável).
- Transcrição com `faster-whisper` (temperature=0, VAD opcional, word timestamps quando disponíveis).
- JSON mestre com segmentos `{id, start, end, ja_raw, romaji, translations{...}}`.
- Romanização por `pykakasi`.
- Tradução pluggable: modo `llm` (local `llama.cpp` ou API genérica) e modo `draft+postedit` (esboço NLLB + pós-edição LLM).
- Exporta SRT/VTT/ASS, suporta bilíngue (ex: JP + PT-BR). Quebra de linha em ~42 caracteres e no máximo 2 linhas.
- Soft-mux em MKV e hard-burn via ffmpeg+libass.
- Cache por workdir; não repete etapas se `master.json` já existe.

## Instalação
Requisitos: Python 3.11+, ffmpeg disponível no PATH (Windows). Opcional: `faster-whisper` para ASR, `requests` para provider API.

```bash
python -m venv .venv
.venv\\Scripts\\activate  # PowerShell
pip install -e .
# Extras
pip install jp2subs[asr]     # faster-whisper
pip install jp2subs[llm]     # requests para API genérica
pip install jp2subs[gui]     # PySide6 para a interface desktop
```

Modelos:
- **faster-whisper**: baixe um modelo (ex: `large-v3`) e deixe o cache padrão (~AppData/Local/whisper).
- **llama.cpp**: defina `JP2SUBS_LLAMA_BINARY` para o executável e `JP2SUBS_LLAMA_MODEL` para o arquivo GGUF.
- **NLLB** (rascunho opcional): utilize seu executor preferido offline (hook manual no provider ou pré-processo).

## Uso rápido
```bash
# Interface gráfica
jp2subs ui

# 1) Ingestão (extrai áudio para workdir)
jp2subs ingest input.mkv --workdir workdir

# 2) Transcrição
jp2subs transcribe workdir/audio.flac --workdir workdir --model-size large-v3

# 3) Romanização
jp2subs romanize workdir/master.json --workdir workdir

# 4) Tradução (ex.: pt-BR e en, provider local via llama.cpp)
jp2subs translate workdir/master.json --to pt-BR --to en --mode llm --provider local --block-size 20

# 5) Exportar legendas bilíngues (JP + PT-BR)
jp2subs export workdir/master.json --format ass --lang pt-BR --bilingual ja --out workdir/subs_pt-BR.ass

# 6) Gere/edite as legendas e depois escolha o modo secundário
#    Softcode (mkv/mp4 sem reencode), hardcode (burn-in) ou sidecar (somente copiar)
jp2subs softcode input.mkv workdir/subs_pt-BR.ass --same-name --container mkv
jp2subs hardcode input.mkv workdir/subs_pt-BR.ass --same-name --suffix .hard --crf 18
jp2subs sidecar input.mkv workdir/subs_pt-BR.ass --out-dir releases
```

## Gerar executável Windows (.exe)
Instale PyInstaller e o extra `gui`, depois execute o script PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
python -m pip install jp2subs[gui] pyinstaller
pwsh scripts/build_exe.ps1
```

## Screenshots
*(adicione suas capturas aqui; placeholders para catálogo)*

## Formato do JSON mestre
Ver [`examples/master.sample.json`](examples/master.sample.json) para um contrato completo:
```json
{
  "meta": {"source": "...", "created_at": "...", "tool_versions": {...}, "settings": {...}},
  "segments": [
    {"id": 1, "start": 12.34, "end": 15.82, "ja_raw": "...", "romaji": "...", "translations": {"pt-BR": "..."}}
  ]
}
```

## Prompts internos (qualidade e fidelidade)
- **Normalização mínima (opcional)**: preserva tiques, sem reescrever.
- **Tradução fiel-natural (blocos)**: reforça fidelidade, não inventar conteúdo, manter interjeições e honoríficos; um output por linha.
- **Pós-edição (draft+postedit)**: melhora tradução rascunho mantendo sentido e tics.
Os textos completos estão em `src/jp2subs/translation.py`.

## Qualidade das traduções
- Fidelidade prioritária: sem invenções ou cortes de tics (えっと, あの, うん etc.).
- Manter repetições e hesitações, nomes próprios e honoríficos salvo glossário.
- Glossário opcional por JSON (`--glossary`), aplicado pelo provider.

## Estrutura do repositório
- `src/jp2subs/`: código-fonte (CLI, ASR wrapper, romanização, tradução, exportadores, ffmpeg helpers)
- `examples/`: `master.sample.json` e dicas de uso
- `configs/`: espaço para presets (adicione os seus)
- `.github/workflows/ci.yml`: lint básico e testes
- `tests/`: testes unitários de schema e writers

## Execução de testes
```bash
pip install -e .
pip install pytest
pytest
```

## Modo secundário de legendagem
- Depois de exportar/editar as legendas, use os comandos dedicados para aplicá-las ao vídeo:
  - `jp2subs softcode <video> <subs> --same-name --container mkv` para mux (sem reencode, usa mov_text automaticamente para MP4).
  - `jp2subs hardcode <video> <subs> --suffix .hard --crf 18` para burn-in com libass, respeitando ASS/SRT/VTT.
  - `jp2subs sidecar <video> <subs> --out-dir player\downloads` para apenas copiar/renomear a legenda, mantendo compatibilidade com players que leem arquivos separados.


## Roadmap sugerido
- Integrar NLLB direto (onnx/ct2) para draft.
- Adicionar presets de estilos ASS específicos para anime.
- UI opcional (futuro).

## Licença
MIT (ver [LICENSE](LICENSE)).
