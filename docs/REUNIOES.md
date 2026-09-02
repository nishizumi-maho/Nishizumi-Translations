# Nishizumi Reuniões (experimental)

Transcreve a gravação de uma reunião em **português do Brasil** e devolve um
`.txt` em estilo legenda: horário de fala, quem falou e o que foi dito.

Ele **só transcreve**. Não traduz, não gera legenda em vídeo, não resume, não
edita. É um irmão menor e propositalmente estreito do Nishizumi Translations,
publicado como versão experimental.

Tudo roda na sua máquina: o áudio não é enviado para lugar nenhum.

```
TRANSCRIÇÃO DA REUNIÃO
────────────────────────────────────────────────────────────────────────
Arquivo......: reuniao-semanal.m4a
Duração......: 1 h 12 min 4 s
Gerada em....: 02/09/2026 às 14:33
Modelo.......: large-v3-turbo (Whisper)
Idioma.......: português do Brasil
Interlocutores: 3 (Ana, Interlocutor 2, Interlocutor 3)
────────────────────────────────────────────────────────────────────────

[00:00:04 → 00:00:12]  Ana
Bom dia a todos. Vamos começar pela revisão do trimestre.

[00:00:13 → 00:00:29]  Interlocutor 2
Eu fecho os números até sexta e mando por e-mail.
```

## Instalar

### Windows

Baixe `Nishizumi-Reunioes-Setup-<versão>.exe` no
[pré-lançamento experimental](https://github.com/nishizumi-maho/Nishizumi-Translations/releases)
e execute.

- Instala por usuário, sem pedir senha de administrador.
- O instalador pergunta duas pastas: a do programa e a dos modelos. Aponte a
  segunda para um disco com espaço — são alguns gigabytes.
- Convive sem conflito com o Nishizumi Translations instalado.

### Linux

Baixe `Nishizumi-Reunioes-<versão>-linux-x64.tar.gz`, extraia e execute
`NishizumiReunioes`.

### A partir do código

```bash
git clone https://github.com/nishizumi-maho/Nishizumi-Translations.git
cd Nishizumi-Translations
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[gui,asr,interlocutores]"
reuniao preparar     # baixa FFmpeg, o modelo recomendado e o pacote de vozes
reuniao ui
```

Precisa de Python 3.11 ou mais novo.

## Primeiro uso

1. Abra o aplicativo e vá em **Componentes**.
2. Baixe o **FFmpeg**, um **modelo de transcrição** e, se quiser saber quem
   falou, a **Identificação de interlocutores** (37 MB).
3. Volte em **Transcrever**, arraste a gravação e clique em **Transcrever**.

Os modelos ficam na mesma pasta usada pelo Nishizumi Translations. Se você já
usa o outro aplicativo, o que estiver baixado é reaproveitado — nada é baixado
duas vezes.

### Qual modelo escolher

| Modelo | Tamanho | Quando usar |
| --- | --- | --- |
| Large v3 Turbo | 1,5 GB | O padrão. Rápido e preciso o bastante para quase tudo. |
| Large v3 | 2,9 GB | Quando a gravação é ruim e você tem GPU (ou paciência). |
| Medium | 1,4 GB | Sem GPU, com ruído de fundo. |
| Small | 464 MB | Sem GPU, gravação limpa. |
| Base / Tiny | 141 / 75 MB | Só para testar se está tudo funcionando. |

Sem uma placa NVIDIA, uma reunião de uma hora com o Large v3 pode levar horas.
O Turbo é várias vezes mais rápido e quase tão bom.

## Como os interlocutores são identificados

O pacote de vozes usa dois modelos ONNX: um separa a gravação em trechos de
fala e marca onde a voz muda; o outro transforma cada trecho em uma
"impressão digital" de voz. Trechos com impressões parecidas viram a mesma
pessoa. É automático e independe do idioma.

O número de participantes é descoberto sozinho — você não informa quantos
são. Isso é de propósito: o motor aceita um número fixo de vozes, mas medindo
o resultado ele erra mais assim do que no automático (numa gravação de duas
pessoas que o automático separa certo, pedir "2" devolve 1).

O que você regula é a **Separação de vozes**, e só quando o resultado sair
errado:

- **Separar mais** — duas pessoas viraram uma só.
- **Juntar mais** — uma pessoa virou duas.

Preencha também o campo **Nomes** com `Ana, João, Carla` na ordem em que cada
um fala pela primeira vez, e o texto sai com os nomes no lugar de
"Interlocutor 1".

O programa **não reconhece pessoas**: ele só distingue vozes dentro daquela
gravação. Vozes muito parecidas, muita conversa cruzada ou um microfone
distante atrapalham.

Sem o pacote instalado, a transcrição sai normalmente — só sem os nomes, com os
horários de sempre.

## Pela linha de comando

```bash
reuniao transcrever reuniao.m4a
reuniao transcrever reuniao.m4a --nomes "Ana,João,Carla,Beto"
reuniao transcrever *.mp3 --saida ~/transcricoes --srt --formato linhas
reuniao componentes            # o que já está instalado
reuniao instalar model:medium  # baixa um componente pela chave
reuniao config                 # mostra as preferências salvas
```

Opções úteis do `transcrever`:

| Opção | Para quê |
| --- | --- |
| `--nomes "Ana,João"` | Nomes na ordem da primeira fala. |
| `--separacao 0.35` | Separa mais as vozes. Acima de 0.5 junta mais. |
| `--formato linhas` | Uma linha por fala, bom para `grep` e comparação. |
| `--srt` `--vtt` `--json` | Formatos extras além do `.txt`. |
| `--dispositivo cpu` | Força o processador quando a GPU dá problema. |
| `--prompt "..."` | Contexto para o Whisper acertar siglas e nomes próprios. |
| `--sem-interlocutores` | Só o texto com horários, sem separar vozes. |

## O que sai

Por padrão, um `.txt` ao lado da gravação. Uma transcrição anterior nunca é
sobrescrita: a segunda vira `reuniao (2).txt`.

- **Blocos** (padrão): horário e nome numa linha, a fala embaixo, quebrada em
  96 colunas. É o formato para ler e imprimir.
- **Linhas**: `[00:00:04 → 00:00:12] Ana: texto` — uma linha por fala.
- **`.srt` / `.vtt`**: legendas, com trechos curtos em vez dos blocos longos.
- **`.json`**: os mesmos dados com campos em português, para processar depois.

O `.txt` é salvo com BOM UTF-8, que é o que faz o Bloco de Notas e o Excel
mostrarem os acentos corretamente no Windows.

## Limitações conhecidas

- O Whisper às vezes inventa texto em trechos de silêncio ou ruído. A opção
  **Evitar repetições** (ligada por padrão) reduz bastante o problema em
  gravações longas.
- Conversa cruzada (duas pessoas falando juntas) é atribuída a uma voz só.
- Números, siglas e nomes próprios são o que mais sai errado. Colocá-los no
  campo **Contexto** ajuda o modelo a acertar a grafia.
- Não há atualização automática: esta versão é publicada como pré-lançamento
  oculto e é atualizada baixando a próxima manualmente.

## Para quem for mexer no código

| Onde | O que faz |
| --- | --- |
| `src/reuniao/pipeline.py` | Orquestra: preparar → transcrever → interlocutores → salvar. |
| `src/reuniao/transcribe.py` | Whisper preso ao português. |
| `src/reuniao/diarize.py` | sherpa-onnx: separa e agrupa as vozes. |
| `src/reuniao/speakers.py` | Casa palavra a palavra com a voz de quem falou. |
| `src/reuniao/writers.py` | Escreve `.txt`, `.srt`, `.vtt` e `.json`. |
| `src/reuniao/components.py` | O que a página Componentes oferece. |
| `src/reuniao/gui/` | A janela. |
| `build_reuniao.py` | Empacota com PyInstaller. |
| `installer/reuniao.iss` | Instalador do Windows. |
| `.github/workflows/release-reuniao.yml` | Publica o pré-lançamento oculto. |

O download de componentes, a pasta dos modelos e o tema da interface são
compartilhados com o `jp2subs`. O resto é independente: o aplicativo de
reuniões não carrega o pipeline de legendas em momento algum.

Publicar uma versão nova:

```bash
# 1. altere __version__ em src/reuniao/__init__.py
# 2. crie e envie a tag correspondente
git tag reuniao-v0.2.0 && git push origin reuniao-v0.2.0
```

Quando criar tags não for possível (token restrito, proteção de repositório),
empurre uma branch de publicação em vez disso — o workflow cria a tag a partir
da versão do pacote:

```bash
git push origin HEAD:refs/heads/publicar/reuniao-v0.2.0
```

De qualquer um dos dois jeitos, o workflow confere se a tag bate com a versão
do pacote, monta os pacotes de Windows e Linux e cria um release **rascunho e
pré-lançamento** — visível só para quem tem acesso de escrita ao repositório.
Se a tag já existir, é o commit dela que é empacotado.
