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

### Windows portátil (sem instalar nada)

Baixe `Nishizumi-Reunioes-<versão>-windows-portatil.zip`, extraia numa pasta
sua — Documentos, Área de Trabalho, um pen drive, um segundo disco — e abra
`NishizumiReunioes.exe`.

É o caminho para computador de trabalho, onde você não é administrador. Nada
é instalado, nada vai para o registro do Windows e nada é gravado em
`AppData`: os modelos, o FFmpeg e as suas preferências ficam todos na subpasta
`dados`, ao lado do programa. Dá para copiar a pasta inteira para outra
máquina com tudo já baixado dentro.

Quem liga esse comportamento é o arquivo `portatil.txt`, que vem junto.
Apague-o e o programa volta a guardar os modelos na pasta do usuário.

Se a pasta escolhida não aceitar gravação, o aplicativo avisa na página
**Componentes** e usa a pasta do usuário — ele não quebra. Nesse caso, mova o
programa para uma pasta realmente sua.

### Windows com instalador

Baixe `Nishizumi-Reunioes-Setup-<versão>.exe` e execute.

- Instala por usuário, sem pedir senha de administrador.
- O instalador pergunta duas pastas: a do programa e a dos modelos. Aponte a
  segunda para um disco com espaço — são alguns gigabytes.
- Convive sem conflito com o Nishizumi Translations instalado, e reaproveita
  os modelos que ele já tiver baixado.

### Linux

Baixe `Nishizumi-Reunioes-<versão>-linux-x64-portatil.tar.gz`, extraia e
execute `NishizumiReunioes`. Vale o mesmo do portátil do Windows: tudo fica na
subpasta `dados`.

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

Na versão instalada, os modelos ficam na mesma pasta usada pelo Nishizumi
Translations: se você já usa o outro aplicativo, o que estiver baixado é
reaproveitado. No modo portátil eles ficam dentro da pasta do programa, que é
o que torna a pasta autossuficiente.

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

O aplicativo carrega modelos no formato **CTranslate2**. A maioria dos
fine-tunes publicados no Hugging Face está em formato PyTorch e não carrega
direto; seria preciso convertê-los antes com `ct2-transformers-converter`.

## O que mais melhora o resultado

Em ordem de impacto, medido ou fundamentado:

**1. Preencha "Nomes e siglas".** Um termo por linha: pessoas, projetos,
clientes, siglas internas. A lista é passada ao reconhecimento como dica *e*
usada depois para conferir a grafia. Nome próprio e sigla são o que o Whisper
mais erra e o que uma ata mais precisa acertar. Sozinho, é o maior ganho
disponível.

**2. Equalizar o volume** (ligado por padrão). Numa sala com um gravador só,
quem está longe do aparelho sai baixo — e volume baixo o Whisper erra bem mais
que ruído. O preparo emparelha os volumes e corta o ronco de ar-condicionado e
mesa. De propósito **não** há redução de ruído: o Whisper foi treinado com
áudio ruidoso, e filtrar demais remove as pistas de que ele depende.

**3. Uma faixa por participante**, quando der. Se a reunião for por Teams,
Meet ou Zoom com gravação separada por pessoa, marque **Faixas** e coloque
todos os arquivos na fila: viram uma reunião só, cada um um interlocutor. Aí
não há adivinhação de voz nenhuma, e a fala cruzada para de comer palavras.
É o melhor resultado possível — mas só serve com as faixas separadas em mãos.

**4. Modelo maior e beam maior.** O beam já vem em 8 (o usual é 5): o modelo
pesa mais hipóteses antes de decidir cada trecho, ao custo de cerca de um terço
a mais de tempo.

**5. A gravação em si** manda em tudo. Nenhum modelo recupera o que o
microfone não capturou. Gravador no meio da mesa, perto de quem mais fala,
vale mais que qualquer ajuste desta lista.

O que **não** compensa: redução de ruído agressiva, e trocar o modelo genérico
por um fine-tune de português treinado em fala lida — reunião é fala
espontânea, com gente falando por cima e microfone longe, e um modelo afinado
em áudio limpo costuma piorar aí.

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

Depois de separar, o aplicativo ainda **consolida** o resultado. Agrupar fala
curta e ruidosa inventa gente: uma tosse, uma sobreposição ou uma palavra do
outro lado da sala viram uma "voz" própria. Numa reunião real de 2h38, das 36
vozes encontradas, 23 somavam dois minutos entre todas. Quem tem tempo de fala
irrisório e aparece cercado por uma mesma outra pessoa é tratado como fragmento
dela: o texto continua no lugar, só muda o nome em cima. Quando o trecho está
entre duas pessoas **diferentes**, ele fica como está — ali chutar seria pior.

O programa **não reconhece pessoas**: ele só distingue vozes dentro daquela
gravação. Vozes muito parecidas, muita conversa cruzada ou um microfone
distante atrapalham.

Sem o pacote instalado, a transcrição sai normalmente — só sem os nomes, com os
horários de sempre.

## Revisar ouvindo

A aba **Revisar** abre a transcrição com a gravação junto. Clique numa fala e
o áudio pula para aquele momento; com **Acompanhar** ligado a lista rola
sozinha seguindo o que está tocando. Dá para procurar no texto, e a velocidade
vai até 2×.

É assim que se resolvem as duas perguntas que o texto não responde sozinho:
quem é o "Interlocutor 3", e se um trecho marcado com `[?]` diz mesmo aquilo.
Para reabrir uma transcrição antiga, use **Abrir transcrição...** e escolha o
`.json` — deixe a gravação na mesma pasta que ele acha sozinho.

## O que o texto marca

- **`[?]`** — o reconhecimento saiu com baixa confiança nessa fala. Confira no
  áudio antes de citar. Falas duvidosas nunca são fundidas com as boas, para a
  marca apontar a frase certa e não um parágrafo inteiro.
- **Tempo de fala** no cabeçalho: quanto cada interlocutor falou, em minutos e
  porcentagem.
- **Observações** no cabeçalho: quantas repetições foram descartadas, quantas
  palavras o glossário ajustou, quantas falas soltas foram atribuídas a quem
  falava em volta.

Quando o Whisper entra em loop — a mesma frase repetida por minutos sobre um
silêncio — o filtro reduz a uma ocorrência e registra no cabeçalho.

## Reaproveitar o que já foi transcrito

O reconhecimento é guardado assim que termina, junto dos modelos. Rodar a mesma
gravação de novo com os mesmos ajustes pula direto para a parte rápida, em vez
de refazer a hora de transcrição. Mudar o modelo, o beam, o contexto ou o
glossário invalida o que estava guardado, porque o resultado mudaria.

`reuniao limpar-cache` apaga tudo o que estiver guardado.

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
| `--glossario nomes.txt` | Nomes e siglas, de um arquivo ou separados por vírgula. |
| `--faixas` | Os arquivos são faixas de uma reunião, uma por pessoa. |
| `--sem-equalizar` | Não emparelhar o volume no preparo. |
| `--sem-duvidas` | Não marcar `[?]` nos trechos de baixa confiança. |
| `--sem-reaproveitar` | Ignorar a transcrição guardada e refazer. |
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
| `src/reuniao/portable.py` | Modo portátil: tudo dentro da pasta do programa. |
| `src/reuniao/cleanup.py` | Filtro de repetições e correção pelo glossário. |
| `src/reuniao/cache.py` | Guarda o reconhecimento para não refazê-lo. |
| `src/reuniao/review.py` | Lê uma transcrição de volta para a aba Revisar. |
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
