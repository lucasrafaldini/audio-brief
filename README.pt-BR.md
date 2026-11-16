# 🎧 audio-brief

> 🌐 [English](README.md) · **Português (Brasil)** · [Español](README.es.md)

[![Hacktoberfest](https://img.shields.io/badge/Hacktoberfest-2026-f74700?style=flat-square)](https://hacktoberfest.com)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

Grave ou transcreva áudio com **OpenAI Whisper** e receba automaticamente um
**resumo**, um **mapa mental**, **palavras-chave** e transcrições prontas
(`.txt`, `.srt`, `.vtt`, `.json`) — tudo em um único comando. Sem chaves de API,
funciona offline (após o primeiro download do modelo).

Funciona em **Linux** e **macOS**.

## ✨ Recursos

- 🎙️ Grave do microfone ou transcreva arquivos de áudio existentes
- 🌍 Detecção automática de idioma (ou force com `--language`)
- 🧠 Resumo extrativo, extração de palavras-chave e mapas mentais (Markmap + Mermaid)
- 📄 Legendas em SRT/VTT + `report.md` e `report.html` tudo-em-um
- 🔗 Nota pronta para o Obsidian (`obsidian.md`) com callout de resumo, `[[wiki-links]]` para as principais palavras-chave e uma árvore de tópicos com timestamps para gravações longas com vários assuntos (ex.: grupos de conversa)
- 🗣️ Dois motores de fala: Whisper (preciso, muitos idiomas) ou PocketSphinx (pequeno, totalmente offline, inglês; `--engine pocketsphinx`)
- 📊 Benchmarks de velocidade e qualidade dos tópicos (`make bench`, [resultados](benchmarks/RESULTS.md))
- 🩺 Comando `doctor` verifica seu ambiente (Whisper, ffmpeg, microfone)
- ⚡ Processamento paralelo: vários arquivos (e gravações longas, divididas nas pausas) são transcritos por processos de trabalho dimensionados pela sua CPU e memória; cada arquivo é resumido assim que fica pronto (`--jobs auto`, [detalhes](#processamento-paralelo---jobs))
- 🖥️ CLI amigável: padrões sensatos, zero perguntas quando usado em pipe/CI

## 🚀 Início rápido

Requer **Python 3.10+** e **ffmpeg** (o Whisper usa para ler os arquivos de áudio;
`brew install ffmpeg` no macOS, `sudo apt install ffmpeg` no Debian/Ubuntu).

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief
./install.sh          # cria .venv, instala audio-brief + Whisper (PyTorch: download de 1-3 GB)
```

O `install.sh` mostra cada etapa com a duração e verifica o resultado; se algo falhar,
a última linha diz a etapa e como resolver (falta de `python3-venv`, Python antigo,
ffmpeg ausente...). `./install.sh --dev` adiciona o pytest, `--bench` as ferramentas
de benchmark. No Linux, o PyTorch padrão do pip inclui CUDA (o ambiente fica com cerca
de 5-6 GB); para instalar só para CPU rode antes `python3 -m venv .venv &&
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu`.


Instalação leve: `./install.sh --engine pocketsphinx` (ou `make setup-light`) usa o
PocketSphinx no lugar do Whisper: cerca de 70 MB instalados em cerca de um minuto em vez de
5-6 GB, só inglês e bem menos preciso em conversas (veja
[Motores de reconhecimento de fala](#motores-de-reconhecimento-de-fala)). `--engine both`
instala os dois.

```mermaid
flowchart LR
    s1["1/5 Python ≥ 3.10 + venv"] --> s2["2/5 .venv"] --> s3["3/5 pip"] --> s4["4/5 audio-brief +<br/>Whisper + PyTorch"] --> s5["5/5 verifica imports + ffmpeg"]
    s5 --> ok(["✔ resumo: versões, tamanho, tempo"])
    s1 & s2 & s4 & s5 -. "em caso de erro" .-> err(["✘ etapa que falhou + como resolver"])
```


Depois:

```bash
./audio-brief transcribe reuniao.mp3       # escolhe modelo/idioma interativamente
./audio-brief transcribe reuniao.mp3 --model base --language pt
./audio-brief record 120                    # grava 2 minutos, depois transcreve
```

Após o `install.sh`, você também pode adicionar o venv ao seu PATH e usar o
comando diretamente:

```bash
export PATH="$PWD/.venv/bin:$PATH"
audio-brief --help
```

### Outras formas de instalar

```bash
pip install '.[whisper]'          # no ambiente atual (motor Whisper)
pip install '.[pocketsphinx]'     # ou o motor leve PocketSphinx (os dois: '.[whisper,pocketsphinx]')
pipx install '.[whisper]'         # instalação isolada do CLI
```

Um `pip install .` simples não instala nenhum motor de fala (os recursos de texto não precisam).

## 📖 Uso

```
audio-brief record [segundos] [--engine E] [--model M] [--language L] [--out DIR] [--keep-raw] [--min-chars N]
audio-brief transcribe <arquivo> [arquivo2 ...] [--jobs N|auto] [--split-long|--no-split-long] [--engine E] [--model M] [--language L] [--out DIR] [--min-chars N]
audio-brief doctor
audio-brief --version
```

| Opção | Significado |
|--------|---------|
| `--engine E` | `whisper` (padrão; ou `$AUDIO_BRIEF_ENGINE`) ou `pocketsphinx` (leve, offline, só inglês). Veja [Motores de reconhecimento de fala](#motores-de-reconhecimento-de-fala) |
| `--model` | `tiny` (rápido/impreciso) → `base` → `small` → `medium` → `large`/`turbo` (preciso, mais lento); só Whisper |
| `--language` | Código ISO de 2–3 letras (ex.: `en`, `pt`, `es`). Pula a pergunta; detecta automático se não definido |
| `--out DIR` | Escolhe o diretório de saída |
| `--jobs N\|auto` | Processos de trabalho para o reconhecimento de fala (só `transcribe`). Padrão `auto`: escolhido pelos núcleos de CPU, memória livre e tamanho do motor; `1` = um arquivo depois do outro. Veja [Processamento paralelo](#processamento-paralelo---jobs) |
| `--split-long` / `--no-split-long` | Divide arquivos longos nas pausas para que vários processos os compartilhem (padrão: ligado para PocketSphinx, desligado para Whisper) |
| `--summary-n N` | Máximo de frases no resumo (padrão: 8) |
| `--keywords-n N` | Máximo de palavras-chave extraídas (padrão: 15) |
| `--min-chars N` | Ignora frases com menos de N caracteres ("Tá.", "kkk") no resumo, mapa mental e árvore de tópicos (padrão: 20, `0` mantém todas) |
| `--keep-raw` | Mantém o `.wav` gravado dentro da pasta de saída (só `record`) |

Rode `audio-brief doctor` primeiro se algo não funcionar — ele verifica
Python, os motores de fala, ffmpeg, backends de gravação e (no macOS) lista os dispositivos de áudio.

Exemplos:

```bash
# um arquivo, inglês, modelo medium
audio-brief transcribe aula.wav --model medium --language en

# uma pasta de gravações, processos escolhidos automaticamente (o plano é impresso antes)
audio-brief transcribe reunioes/*.mp3

# no máximo dois por vez, p.ex. para manter a máquina utilizável
audio-brief transcribe a.mp3 b.mp3 c.mp3 --jobs 2
```

Quando executado interativamente, você será perguntado sobre idioma e modelo
uma vez; quando usado em pipe (CI, scripts), usa auto-detect + `base`.

### Relatório de processamento

Depois de cada arquivo o audio-brief mostra o que fez e quanto tempo levou, por
exemplo para um grupo de conversa de 9.605 palavras (o tempo do Whisper depende do
modelo e da máquina):

```
--- Processing report ---
  transcription (whisper): …s for …s of audio (…x real time)
  text: 9,605 words in 736 segments (transcript had little punctuation: analysed per speech segment)
  found: 8 top-level topics, 9 mind-map branches, 11 files
  analysis + writing: 0.33s  (units 3 ms, specificity 91 ms, summary 29 ms, keywords 24 ms, topic tree 45 ms, timestamps 2 ms, mind map 37 ms, grouping 5 ms, writing files 92 ms)
```

## 📂 Saídas

Os arquivos caem em `audio-brief-<timestamp>/` no diretório atual (ou `--out DIR`),
uma pasta `run-<n>/` por arquivo transcrito, numerada na ordem em que os arquivos foram passados:

| Arquivo | Conteúdo |
|------|---------|
| `transcript.txt` | Transcrição em texto com timestamps |
| `transcript.srt` / `.vtt` | Legendas |
| `transcript.json` | Dados brutos dos segmentos |
| `summary.md` | Frases-chave, ranqueadas (fragmentos com menos de 20 caracteres são ignorados) |
| `keywords.md` | Principais palavras-chave e expressões de duas palavras recorrentes, com quantas vezes aparecem |
| `mindmap.md` | Mapa mental: tópico › subtópico › frase (cole em [markmap.js.org](https://markmap.js.org)) |
| `mindmap.mmd` | Mapa mental em Mermaid ([mermaid.live](https://mermaid.live)) |
| `report.md` | Tudo em um único Markdown |
| `report.html` | Mesmo relatório como página web autocontida (sem precisar de visualizador) |
| `obsidian.md` | Nota do Obsidian: callout `> [!summary]`, `[[wiki-links]]` para as 10 principais palavras-chave, árvore `## Topics` de wiki-links aninhados com timestamps, transcrição recolhível |

## 🏗️ Arquitetura

### Estrutura do projeto

Tanto `./audio-brief` (o launcher do repositório) quanto o comando
`audio-brief` instalado chegam em `audio_brief/cli.py`. A CLI cuida da gravação e
do reconhecimento de fala (`asr.py`; `parallel.py` distribui arquivos muitos ou longos
entre processos de trabalho); todo o processamento de texto é offline e sem dependências. A pasta
`benchmarks/` mede sua velocidade e qualidade (veja [Benchmarks](#-benchmarks)).

```mermaid
flowchart LR
    user(["Você"]) --> launcher["./audio-brief<br/>(script launcher)"]
    user --> entry["audio-brief<br/>(entry point do pip)"]
    launcher --> cli
    entry --> cli

    subgraph pkg["audio_brief/"]
        cli["cli.py<br/>record · transcribe · doctor"]
        recorder["recorder.py<br/>arecord · ffmpeg · sox rec"]
        asr["asr.py<br/>whisper · pocketsphinx"]
        par["parallel.py<br/>plano · processos de trabalho · junção"]
        writers["writers.py<br/>write_all + um writer por formato"]
        textproc["textproc.py<br/>analyze · term_specificity · summarize ·<br/>extract_keywords · build_mindmap · topic_tree"]
    end

    cli --> recorder
    cli --> asr
    cli --> par
    par --> asr
    asr --> whisper[["openai-whisper"]]
    asr --> pocketsphinx[["pocketsphinx"]]
    cli --> writers
    writers --> textproc

    subgraph bench["benchmarks/ (make bench)"]
        fetch["fetch_data.py<br/>corpora fixados e verificados"]
        run["run.py → RESULTS.md<br/>+ results.json"]
        tasks["tasks.py · baselines.py<br/>real.py · stats.py · metrics.py<br/>asr_bench.py · parallel_bench.py"]
        datasets["datasets.py · synthetic.py<br/>chats sintéticos controlados"]
    end

    subgraph scripts["scripts/ (install.sh, Makefile)"]
        lib["lib.sh · run.sh · ensure-venv.sh<br/>etapas registradas e cronometradas"]
    end

    run --> tasks
    run --> datasets
    tasks --> textproc
    fetch -.-> tasks

    subgraph tests["tests/ (pytest, offline)"]
        t_cli["test_cli.py"]
        t_rec["test_recorder.py"]
        t_wr["test_writers.py"]
        t_tp["test_textproc.py"]
        t_gc["test_group_chat.py"]
        t_bm["test_benchmarks.py"]
        t_asr["test_asr.py"]
        t_par["test_parallel.py"]
        t_doc["test_docs.py<br/>(mermaid em todo .md)"]
    end

    t_cli -.-> cli
    t_rec -.-> recorder
    t_wr -.-> writers
    t_tp -.-> textproc
    t_gc -.-> datasets
    t_bm -.-> run
    t_bm -.-> tasks
    t_asr -.-> asr
    t_par -.-> par
```

### Pipeline de processamento

`writers.write_all()` chama `textproc.analyze()` uma vez por arquivo. Ela escolhe as
unidades de análise (frases, ou os segmentos do Whisper quando a transcrição quase não
tem pontuação, porque aí as frases só podem ser cortadas em blocos de 30 palavras),
pontua a especificidade de cada palavra e calcula resumo, palavras-chave, árvore de
tópicos (com timestamps) e mapa mental a partir disso. `--min-chars` (padrão 20)
mantém fragmentos curtos fora do resumo, do mapa mental e da árvore de tópicos.

```mermaid
flowchart TD
    mic(["record N"]) --> rec["recorder.record()"] --> wav[/"arquivo WAV"/]
    file(["transcribe FILE"]) --> wav
    wav --> engine["asr engine (--engine)<br/>Whisper or PocketSphinx"]
    engine --> text[/"texto + segmentos"/]
    text --> all["writers.write_all()<br/>min_char_length = --min-chars (20)"]
    all --> units

    subgraph an["textproc.analyze()"]
        units["analysis_units()<br/>frases, ou segmentos se sem pontuação"] --> spec["term_specificity()"]
        units --> sum["summarize()"]
        spec --> kw["extract_keywords()"]
        spec --> tt["topic_tree()<br/>+ attach_timestamps()"]
        spec --> mm["build_mindmap()"]
        tt --> grp["group_mindmap()"]
        mm --> grp
    end

    all --> tr["transcript.txt / .srt / .vtt / .json"]
    sum --> s_md["summary.md"]
    kw --> k_md["keywords.md"]
    grp --> m_md["mindmap.md / mindmap.mmd"]
    sum & kw & m_md --> rep["report.md / report.html"]
    sum & kw & tt --> obs["obsidian.md"]
```

### Motores de reconhecimento de fala

`audio_brief/asr.py` coloca os dois motores atrás de uma única interface que devolve texto,
segmentos com tempo, idioma e duração; o resto do pipeline não sabe qual rodou. O Whisper
continua sendo o padrão. O PocketSphinx (CMU Sphinx, licença BSD) é um reconhecedor
estatístico independente e mais antigo, com um modelo de inglês americano embutido: não
precisa de PyTorch nem de download depois de instalado, mas só reconhece inglês, não põe
pontuação (o audio-brief então analisa por segmento de fala) e erra bem mais, sobretudo em
conversas e áudio de telefone. O áudio chega do ffmpeg em fluxo; a detecção de voz só decide
onde uma fala termina (numa pausa de 0,5 s ou após 20 s): todo trecho é decodificado, então a
fala que o detector perde não se perde. Cada fala é então decodificada inteira, o que é mais
preciso que decodificar ao vivo.

```mermaid
flowchart TD
    a[/"arquivo de áudio"/] --> ff["ffmpeg → PCM 16 kHz mono<br/>(em fluxo)"] --> fr["quadros de 30 ms"]
    fr --> buf["entra no buffer da fala"]
    buf --> vad{"pausa ≥ 0,5 s<br/>ou 20 s atingidos?"}
    vad -- não --> fr
    vad -- sim --> dec["o PocketSphinx decodifica<br/>a fala inteira"]
    dec --> seg["segmento: início · fim · texto"]
    seg --> fr
    seg --> out[/"texto + segmentos + duração"/]
```

Medido em fala real (benchmarks/RESULTS.md seção 6):

| Motor | Palavras erradas: fala lida | Palavras erradas: ligação | Velocidade | Memória | Tamanho instalado |
|---|---|---|---|---|---|
| PocketSphinx 5.1.1 | 27% [20-32%] | 81% | 0,80× o tempo real | 169 MB | 39 MB |
| Whisper (tiny/base) | não medido aqui: os pesos do modelo não puderam ser baixados no ambiente do benchmark; rode `make bench ARGS="--only asr"` numa máquina com internet para comparar | | | | 5.5 GB |

O conjunto de teste é pequeno (152 palavras transcritas): as taxas de fala lida e
de ligação têm intervalos largos e são indicativas. Use o PocketSphinx onde o Whisper não
roda (sem GPU ou espaço em disco, sem rede no primeiro uso) e o áudio é inglês claro; caso
contrário, prefira o Whisper.

### Processamento paralelo (`--jobs`)

`audio-brief transcribe` com vários arquivos, ou com um arquivo longo, planeja o
trabalho antes de começar e imprime o plano com o motivo de cada decisão
(`audio_brief/parallel.py`):

- **Processos, não threads.** O reconhecimento de fala é código de extensão Python
  limitado pela CPU que segura o GIL do Python: duas threads de PocketSphinx rodaram
  1,02× mais rápido que uma. Por isso o reconhecimento roda em processos de trabalho,
  cada um carregando seu motor uma vez. Threads só são usadas para esperar o
  ffprobe/ffmpeg (ler durações, achar pausas).
- **Quantos processos.** `--jobs auto` (o padrão) usa o menor entre o que os núcleos de
  CPU e a memória livre permitem: ~0,25 GB por processo PocketSphinx (medido) e, para
  o Whisper, os tamanhos de modelo publicados pela OpenAI (1 GB para `tiny`/`base` até
  10 GB para `large`; não medidos aqui). Cada processo Whisper também recebe
  `núcleos ÷ processos` threads do PyTorch, para não disputarem núcleos.
- **Arquivos longos são divididos nas pausas** quando processos ficariam ociosos (uma
  gravação longa, ou uma bem mais longa que as outras): cortes perto de cada 1-10
  minutos, movidos para a pausa mais próxima (`silencedetect` do ffmpeg) para não cortar
  palavras, depois reunidos com os tempos deslocados. Ligado por padrão no PocketSphinx,
  cuja precisão com divisão é medida abaixo; opcional no Whisper (`--split-long`), onde
  não é medida.
- **Trabalho mais longo primeiro**, para que um arquivo longo não comece por último e
  deixe todos esperando.
- **Os resumos se sobrepõem ao reconhecimento.** Assim que todas as partes de um arquivo
  voltam, o processo principal o analisa e grava seus arquivos enquanto os processos
  continuam transcrevendo o resto. A análise é rápida perto do reconhecimento (0,33 s
  para um chat de 9.605 palavras, veja [Relatório de processamento](#relatório-de-processamento)),
  então não precisa de processos próprios.
- **Progresso e falhas.** Uma linha por unidade concluída com estimativa de término; um
  arquivo que falha é relatado e os outros terminam mesmo assim (código de saída 1).

Com um arquivo que não precisa ser dividido, ou `--jobs 1`, os arquivos são processados
um depois do outro no processo principal, exatamente como antes.

```mermaid
flowchart TD
    files[/"arquivos de áudio"/] --> probe["durações via ffprobe<br/>(threads: E/S)"]
    probe --> plan{"make_plan()"}
    res["núcleos de CPU · memória livre<br/>tamanho do motor"] --> plan
    plan -- "1 processo, nada a dividir" --> seq["um depois do outro<br/>(processo principal)"]
    plan -- "caso contrário" --> split{"arquivo longo e<br/>processos ociosos?"}
    split -- sim --> cut["corta nas pausas<br/>(ffmpeg silencedetect)"] --> units
    split -- não --> units["unidades de trabalho,<br/>mais longas primeiro"]
    units --> pool

    subgraph pool["processos de trabalho (--jobs)"]
        w1["processo 1<br/>motor carregado uma vez"]
        w2["processo 2"]
        wn["processo N"]
    end

    pool --> merge["junta as partes<br/>(tempos deslocados)"]
    merge --> analyse["analisa + grava arquivos<br/>(processo principal, enquanto os outros seguem)"]
    analyse --> out[/"run-&lt;n&gt;/ por arquivo"/]
    seq --> out
```

Medido com PocketSphinx em 4 núcleos ([RESULTS.md seção 7](benchmarks/RESULTS.md#7-parallel-processing)):

| Trabalho | Um processo | `--jobs auto` | Aceleração | Precisão |
|---|---:|---:|---:|---|
| Lote: 8 gravações reais, 4,7 min de áudio | 148 s | 38 s (4 processos, 10 unidades: arquivos longos divididos) | **3,9×** | veja a próxima linha |
| Uma gravação, 4,6 min, toda transcrita | 128 s | 57 s (5 partes em 4 processos) | **2,2×** | taxa de erro de palavras 60,5% inteira, 57,4% dividida |

Dividir muda quais palavras o PocketSphinx produz (29% das palavras diferem entre a
transcrição inteira e a dividida) sem piorá-la em relação à referência; é uma gravação só,
então trate como indicativo. As acelerações são execuções únicas numa máquina virtual
compartilhada: uma execução anterior do mesmo benchmark deu 3,8× e 2,8×. A aceleração paralela
do Whisper não foi medida (seus pesos não puderam ser baixados no ambiente do benchmark).

### Filtro de fragmentos no resumo (`min_char_length`)

`textproc.summarize()` (também disponível como `textproc.extract_summary()`)
nunca escolhe frases com menos de `min_char_length` caracteres (padrão `20`),
então muletas como "Tá." ou "Então, né." ficam fora dos resumos. Frases curtas
ainda contam nas frequências de palavras-chave. Use `min_char_length=0` (CLI:
`--min-chars 0`) para desligar o filtro.

```mermaid
flowchart TD
    text[/"texto transcrito"/] --> split["sentences(text)"]
    split --> check{"len(frase) >= min_char_length?"}
    check -- não --> skip["ignorada<br/>(ainda conta nas frequências de termos)"]
    check -- sim --> cand["frases candidatas"]
    cand --> any{"alguma candidata?"}
    any -- não --> empty[/"[] → summary.md mostra<br/>'No summary could be extracted.'"/]
    any -- sim --> score["pontuação = frequência de termos × viés de posição × penalidade de tamanho"]
    score --> dedupe["remove quase-duplicadas<br/>(sobreposição de palavras > 0.7)"]
    dedupe --> top["mantém as n melhores<br/>(ratio / max_sentences)"]
    top --> order[/"resumo na ordem original"/]
```

### Palavras de tópico vs palavras genéricas (especificidade)

Só a frequência não separa tópico de enchimento: num grupo de conversa, "needs",
nomes e dias da semana são tão frequentes quanto "hotel". Mas uma conversa fica num
assunto por um tempo, então uma palavra de tópico prevê do que tratam as frases
*vizinhas*, enquanto uma palavra genérica aparece perto de qualquer coisa (coesão
lexical, a ideia do TextTiling). `textproc.term_specificity()` pontua cada palavra
por quão diferentes as palavras a até 2 unidades dela são da transcrição inteira
(divergência KL, suavizada para não supervalorizar palavras raras). No chat de 2.000
mensagens do benchmark todo substantivo de tópico pontua acima de toda palavra
genérica (0,19 ou mais vs 0,11 ou menos). As palavras-chave são ordenadas
principalmente por ela (veja abaixo), a árvore de tópicos só usa palavras de tópico e o
mapa mental pesa as palavras por ela.

```mermaid
flowchart LR
    w(["uma palavra: hotel · needs"]) --> ctx["palavras a até 2 unidades<br/>de cada menção"]
    all["todas as palavras da transcrição"] --> cmp{"quão diferente?<br/>(divergência KL, suavizada)"}
    ctx --> cmp
    cmp -- "muito: hotel, lisbon" --> topical["de tópico<br/>(alta especificidade)"]
    cmp -- "quase nada: needs, Ana, Friday" --> generic["genérica<br/>(baixa especificidade)"]
    topical --> use["ordem das palavras-chave · vocabulário da árvore ·<br/>pesos do mapa mental"]
```

### Palavras-chave e expressões

`textproc.extract_keywords()` retorna palavras e expressões de duas palavras com quantas
vezes elas realmente aparecem. Uma expressão são duas palavras de conteúdo *vizinhas*
dentro de uma frase que aparecem pelo menos duas vezes, então nada é costurado através
de um ponto final ou de um "the" pulado. Uma expressão que só continua outra já
escolhida ("scored twice" em "striker scored twice") é ignorada, e uma palavra sai
quando uma expressão responde por pelo menos 80% dos seus usos ("bank" → "bank api").
Elas são ordenadas por menções × (0,12 + 0,88 × especificidade), então "hotel" vence um
"needs" mais frequente, enquanto o assunto principal da gravação, mencionado em todo lugar
e por isso *não* específico, continua chegando ao topo (sem essa parcela de 12% de
frequência, o assunto dos artigos reais da Wikipédia ficava bem mais abaixo: MRR 0,44 em
vez de 0,75). A contagem mostrada é sempre a real. Essas também são os `[[wiki-links]]`
do `obsidian.md`. Palavras comuns com pouco conteúdo (a lista SMART de 571 palavras:
"first", "used", "however" ...) são ignoradas, e um termo mencionado pela primeira vez nos 5%
iniciais do texto ganha até o dobro de peso, porque quem fala costuma apresentar o assunto
no começo.

```mermaid
flowchart TD
    text[/"transcrição"/] --> split["analysis units"]
    split --> pairs["pares de palavras de conteúdo vizinhas<br/>dentro de uma unidade"]
    pairs --> rec{"aparece ≥ 2 vezes?"}
    rec -- não --> drop1["não é expressão"]
    rec -- sim --> chain{"só continua uma expressão já escolhida?<br/>(scored twice ⊂ striker scored twice)"}
    chain -- sim --> drop2["ignorada"]
    chain -- não --> phrase["expressão-chave (contagem real)"]
    split --> words["palavras de conteúdo (contagem real)"]
    words --> cover{"≥ 80% dos usos dentro de<br/>uma expressão recorrente?"}
    cover -- sim --> drop3["removida (bank → bank api)"]
    cover -- não --> word["uma palavra: hotel · needs"]
    phrase & word --> rank[/"ordenadas por menções ×<br/>(0,12 + 0,88 × especificidade)<br/>(contagem real exibida)"/]
```

### Agrupamento do mapa mental

`textproc.build_mindmap()` lê as unidades em ordem. Cada uma entra no grupo com as
palavras mais parecidas (similaridade de cosseno ≥ 0,3, com palavras pesadas pela
especificidade para que enchimento compartilhado não decida) ou começa um novo; um
índice de palavras mantém o trabalho linear, e um grupo que não recebe frases há 500 unidades (cerca
de uma hora de fala) deixa de aceitar novas, então gravações muito longas também ficam lineares. Depois `group_mindmap()` coloca esses
subtópicos sob os tópicos de primeiro nível da árvore, então os arquivos ficam tópico ›
subtópico › frase (um tópico com um único subtópico lista as frases direto). No chat de
2.000 mensagens do benchmark isso dá 9 ramos para 8 assuntos com 100% de pureza.
Trecho:

```markdown
## oven / lasagna / basil
### curry / lasagna / recipe
#### I am not sure the spices works with the lasagna.
#### Did anyone check the curry for the lasagna yet.
### basil / oven / spices
#### The spices looks good but the basil is a problem.
```

```mermaid
flowchart TD
    s[/"cada unidade, em ordem"/] --> short{"menor que --min-chars<br/>ou sem palavras de conteúdo?"}
    short -- sim --> skip["fica de fora"]
    short -- não --> cand["grupos que compartilham uma palavra<br/>(índice de palavras)"]
    cand --> cos{"melhor cosseno ≥ 0,3?<br/>(pesado por especificidade)"}
    cos -- sim --> join["entra nesse grupo"]
    cos -- não --> new["começa um grupo novo"]
    join & new --> done(["após a última unidade"])
    done --> clusters["grupos com ≥ 2 unidades = subtópicos<br/>unidades isoladas → ramo de sobras"]
    clusters --> grp{"corresponde a um tópico<br/>da árvore?"}
    grp -- sim --> topic["agrupado sob esse tópico"]
    grp -- não --> alone["continua ramo de primeiro nível"]
    topic & alone --> out[/"mindmap.md / mindmap.mmd<br/>tópico › subtópico › frase"/]
```

### Nota do Obsidian (`obsidian.md`)

`writers.write_obsidian_note(output_dir, text, summary, keywords)` reaproveita o
resumo e as palavras-chave de `write_all`. As palavras-chave são deduplicadas e
limpas de caracteres que o Obsidian não aceita em links (`[ ] | # ^ \ / : * ? " < >`).

```mermaid
flowchart LR
    all["write_all()"] --> note["write_obsidian_note()"]
    note --> file["obsidian.md"]

    subgraph layout["estrutura do obsidian.md"]
        direction TB
        h1["# Audio Brief"]
        callout["&gt; [!summary] Summary<br/>&gt; 1. primeira frase …"]
        links["## Keywords<br/>[[palavra-chave]] · [[outra palavra-chave]] …<br/>(top max_links=10)"]
        quote["&gt; [!quote]- Transcript<br/>(recolhido por padrão)"]
        topics["## Topics<br/>[[league]] (65) · 00:01:21 …<br/>↳ [[football]] (57) · 00:01:21 …"]
        h1 --> callout --> links --> topics --> quote
    end

    file --> layout
```

### Árvore de tópicos (grupos de conversa e gravações longas)

Uma gravação longa que pula de assunto em assunto (um grupo de conversa, uma call semanal)
ganha uma seção `## Topics` no `obsidian.md`: cada assunto vira um ramo de `[[wiki-links]]`
aninhados com o número de unidades que o mencionam e os primeiros timestamps em que aparece.
`textproc.topic_tree()` monta um grafo das palavras-chave de tópico (expressões como
`[[bank api]]` ficam inteiras), ligando dois termos por quanto mais que o acaso eles aparecem
a até uma unidade um do outro (PMI positivo, pares vistos juntos pelo menos 3 vezes). A
detecção de comunidades de Louvain (Blondel et al. 2008) divide esse grafo em tópicos, então
**o número de tópicos vem do texto**. Comunidades que cobrem menos de 5% das unidades de
tópico saem (fragmentos e palavras genéricas), comunidades que aparecem nos mesmos trechos do
texto (1,5× mais que o acaso) viram subtópicos de um assunto, e dentro de um tópico um termo
fica sob um mais frequente quando 70% das suas unidades o têm por perto. Um exemplo real, do
benchmark: três artigos da Wikipédia (Academy Awards, Aardvark, Algeria) intercalados como
uma conversa:

```markdown
## Topics

- [[awards]] (16)
  - [[members]] (10)
    - [[categories]] (6)
  - [[film]] (12)
  - [[academy]] (9)
    - [[oscar]] (4)
- [[burrows]] (7)
  - [[aardvark]] (10)
    - [[termites]] (5)
  - [[season]] (6)
- [[political]] (6)
  - [[islamic]] (7)
  - [[bouteflika]] (5)
- [[ceremony]] (6)
- [[algeria]] (6)
```

```mermaid
flowchart TD
    units[/"unidades de análise"/] --> vocab["palavras-chave + expressões<br/>de tópico (máx. 400)"] --> termgraph["grafo de termos: PMI positivo da<br/>coocorrência a até 1 unidade<br/>(≥ 3 vezes juntos)"] --> louv["comunidades de Louvain<br/>(número de tópicos vem do texto)"]
    louv --> sig{"cobre ≥ 5% das<br/>unidades de tópico?"}
    sig -- não --> drop["fica de fora<br/>(fragmento / genérico)"]
    sig -- sim --> merge{"mesmos trechos do texto<br/>(≥ 1,5× o acaso)?"}
    merge -- sim --> sub["subtópico desse assunto"]
    merge -- não --> topic["tópico"]
    sub & topic --> inside["dentro de um tópico: subsunção<br/>(≥ 70% das unidades por perto)"] --> ts["attach_timestamps()"] --> md[/"## Topics no obsidian.md"/]
```

Como os tópicos são wiki-links simples, gravações salvas no mesmo vault do Obsidian
se conectam pelos assuntos em comum (backlinks e visão de grafo):

```mermaid
flowchart LR
    subgraph vault["Vault do Obsidian"]
        r1["chat-monday/obsidian.md"]
        r2["chat-friday/obsidian.md"]
        lisbon(("lisbon"))
        rent(("rent"))
        movie(("movie"))
    end
    r1 --> lisbon
    r1 --> rent
    r2 --> lisbon
    r2 --> movie
```

Nas transcrições separadas para teste isso dá 0,9-1,5 tópicos de primeiro nível por
assunto real na Wikipédia (2,9 nos posts da Usenet) e nenhum tópico genérico no primeiro
nível. Como mostra o exemplo, um assunto ainda pode se dividir em dois (Academy Awards: awards e
ceremony), um rótulo pode ser uma palavra característica em vez do nome do assunto ("burrows"
para o aardvark) e, com muitos assuntos, alguns se juntam (pureza 65% com 8 tópicos).

## ⚙️ Backends de gravação

Escolhido automaticamente: `arecord` (Linux/ALSA) → `ffmpeg` (macOS via
avfoundation, Linux via ALSA) → `sox rec`. Force um e escolha o microfone:

```bash
AUDIO_BRIEF_RECORDER=ffmpeg AUDIO_BRIEF_MIC=1 audio-brief record 60
# listar entradas de áudio no macOS:
ffmpeg -f avfoundation -list_devices true -i ''
```

## 💡 Tamanho dos modelos

| Modelo | Tamanho | Velocidade (CPU) | Qualidade |
|-------|------|-------------|---------|
| `tiny` | ~75 MB | mais rápido | impreciso |
| `base` | ~150 MB | rápido | ok para um brief |
| `small` | ~500 MB | médio | bom |
| `medium` | ~1,5 GB | lento | ótimo |
| `large`/`turbo` | ~3 GB | mais lento | melhor |
| PocketSphinx (`--engine pocketsphinx`) | ~40 MB, sem PyTorch | ~0,8× o tempo real | só inglês; ~27% de palavras erradas em fala lida limpa, ~81% numa ligação |

## 🍎 App macOS (opcional)

```bash
.venv/bin/pip install py2app
.venv/bin/python setup.py py2app -A
# -> dist/audio-brief.app
```

## 📊 Benchmarks

Qualidade e velocidade são medidas em **dados públicos e reais** com respostas conhecidas, contra
métodos estabelecidos, com intervalos de confiança de 95%. Os parâmetros são escolhidos numa
metade dos corpora e todo número de qualidade abaixo vem da **outra metade, reservada**.
[`benchmarks/RESULTS.md`](benchmarks/RESULTS.md) tem todas as tabelas e gráficos,
[`benchmarks/results.json`](benchmarks/results.json) cada rodada, e
[`benchmarks/METHODOLOGY.md`](benchmarks/METHODOLOGY.md) como cada número é produzido.

```bash
make bench          # ~15 min: instala as ferramentas [bench], baixa os dados e roda tudo
make bench-quick    # rodada rápida de verificação (poucas rodadas para conclusões)
make bench ARGS="--only asr"        # remede só o reconhecimento de fala (os outros resultados são mantidos)
make bench ARGS="--only parallel"   # remede só o processamento paralelo
```

Dados (baixados do PyPI/npm em versões fixas, com checksums verificados): 106 artigos da
Wikipédia, 200 posts da Usenet (20 Newsgroups), 233 discursos do Estado da União e fala real
gravada (trechos de audiolivro, uma ligação telefônica). As transcrições com vários tópicos são
montadas com frases reais de várias fontes (Choi 2000), então o tópico real de cada frase é
conhecido.

```mermaid
flowchart LR
    data[("Wikipédia · Usenet · Estado da União · fala<br/>(fixados, com checksum)")] --> split["metade dev: escolher parâmetros<br/>metade teste: reportar"]
    split --> comp["transcrições multitópico (Choi 2000)<br/>+ documentos únicos + gravações"]
    comp --> sys["audio-brief vs baselines<br/>(mesma entrada, mesmo tamanho)"]
    sys --> met["NMI/ARI · ROUGE · precisão · MRR · WER<br/>tempo · memória"]
    met --> stat["20 rodadas/cenário · bootstrap IC 95%<br/>veredictos pareados"]
    stat --> res[/"RESULTS.md · results.json"/]
```

Principais resultados (metade de teste; valores: média [IC 95%]):

| Tarefa | Dados | Métrica | audio-brief | Baseline mais forte | Veredicto (vitórias/empates/derrotas) |
|---|---|---|---|---|---|
| Descoberta de tópicos (mapa mental) | Wikipédia, 3 tópicos | NMI | 0,53 [0,50; 0,56] | TF-IDF + k-means (true k): 0,41 [0,37; 0,45] | **melhor** (17/0/3) |
| Descoberta de tópicos (mapa mental) | Wikipédia, 5 tópicos | NMI | 0,58 [0,55; 0,61] | TF-IDF + k-means (true k): 0,41 [0,37; 0,45] | **melhor** (20/0/0) |
| Descoberta de tópicos (mapa mental) | Wikipédia, 8 tópicos | NMI | 0,56 [0,53; 0,59] | TF-IDF + k-means (true k): 0,41 [0,38; 0,44] | **melhor** (20/0/0) |
| Descoberta de tópicos (mapa mental) | Usenet, 2 tópicos | NMI | 0,15 [0,14; 0,16] | TF-IDF + k-means (true k): 0,10 [0,08; 0,12] | **melhor** (15/0/5) |
| Precisão das palavras-chave | Wikipédia, 5 tópicos | precision@15 | 84% [79%; 88%] | YAKE: 88% [84%; 92%] | **sem diferença clara** (6/3/11) |
| Assunto principal nas palavras-chave | 38 artigos da Wikipédia | MRR | 0,82 [0,72; 0,91] | YAKE: 0,90 [0,82; 0,97] | **sem diferença clara** (3/24/11) |
| Resumo | 41 introduções da Wikipédia | ROUGE-1 | 0,32 [0,30; 0,34] | LexRank: 0,34 [0,32; 0,35] | **sem diferença clara** (16/0/25) |

O que mudou nesta versão (mesma metade de teste, mesmo harness, código anterior → atual):

| Transcrições | Tópicos de 1º nível por tópico real | Tópicos genéricos no 1º nível | Pureza da árvore | NMI do mapa mental | Precisão das palavras-chave (YAKE) |
|---|---:|---:|---:|---:|---:|
| Wikipédia, 3 tópicos | 3,25 → **1,48** | 39% → **0%** | 90% → **86%** | 0,50 → **0,53** | 86% → **85%** (89%) |
| Wikipédia, 5 tópicos | 2,17 → **1,09** | 33% → **0%** | 84% → **82%** | 0,54 → **0,58** | 83% → **84%** (88%) |
| Wikipédia, 8 tópicos | 1,64 → **0,90** | 18% → **0%** | 67% → **65%** | 0,54 → **0,56** | 76% → **77%** (86%) |
| Usenet, 2 tópicos | 7,53 → **2,90** | 10% → **0%** | 87% → **85%** | 0,13 → **0,15** | 75% → **78%** (91%) |

Assunto principal nas palavras-chave (MRR): 0,73 → **0,82** (YAKE 0,90). Tempo de análise
para 1.000.000 de palavras: 137 s → **34 s**; expoente de escala 1,33 → **1,12**
(1 = linear). Contrapartidas: a pureza da árvore ficou 0,02-0,04 menor, e a precisão das
palavras-chave continua 4-13 pontos atrás do YAKE (na metade dev parecia empatada: a metade
reservada é o motivo de reportar as duas).

```mermaid
xychart-beta
    title "NMI com 5 tópicos (* = recebe o número real de tópicos)"
    x-axis ["audio-brief", "k-means*", "LDA*", "random*", "one cluster"]
    y-axis "NMI" 0 --> 1
    bar [0.578, 0.412, 0.051, 0.029, 0.000]
```

Velocidade em discursos reais: um discurso (mediana de 7.006 palavras) é analisado numa mediana
de **206 ms**; 300.000 palavras levam 8,4 s. O reconhecimento de fala é medido à
parte: veja [Motores de reconhecimento de fala](#motores-de-reconhecimento-de-fala).

O que isso mostra:

- **Agrupar por tópico é o ponto mais forte**: NMI ≈ 0,58 nas misturas da Wikipédia, melhor que TF-IDF + k-means e LDA mesmo recebendo o número real de tópicos; os posts informais da Usenet continuam difíceis (NMI ≈ 0,15).
- **A árvore de tópicos agora tem cerca de um tópico de primeiro nível por assunto** (0,9-1,5 na Wikipédia, 2,9 na Usenet, antes até 3,3 e 7,5) e nenhum tópico genérico no primeiro nível, ao custo de uma pureza um pouco menor.
- **As palavras-chave ficam atrás do YAKE na média** (precisão temática 4-13 pontos menor; MRR do assunto principal 0,82 vs 0,90), embora nesta metade de teste nenhuma das diferenças seja estatisticamente clara.
- **Os resumos empatam com os métodos extrativos clássicos** (sem diferença clara para TextRank e LexRank).
- **Fala**: o PocketSphinx erra cerca de 27% das palavras em fala lida limpa e 81% numa ligação; o Whisper não pôde ser medido offline.
- **Processamento paralelo**: em 4 núcleos, 8 gravações são transcritas 3,9× mais rápido que com um processo, e uma gravação de 4,6 minutos 2,2× mais rápido quando dividida nas pausas, sem perda de precisão (execuções únicas).

## 🧪 Testes

A suíte de testes roda offline (o Whisper é simulado), então não precisa da instalação
completa: num clone novo, `make test` cria sozinho um `.venv` leve com o pytest (sem
mexer no Python do sistema) e reaproveita o ambiente do `make setup` quando existe.
Cada execução registra o interpretador, o comando exato, os 5 testes mais lentos, os
testes pulados com o motivo e o tempo total. `PYTHON=...` usa outro interpretador
(verificado, nunca modificado); `make help` lista todos os alvos.

| Comando | Executa |
|---------|------|
| `make test` | A suíte inteira |
| `make test-writers` | Um módulo, `tests/test_writers.py` (também `cli`, `group_chat` / `group-chat`, `recorder`, `textproc`, `asr`, `parallel`, `docs`, `benchmarks`) |
| `make test-obsidian` | Todo teste cujo nome contém `obsidian`, em todos os módulos |
| `make test K="topic_tree and not empty"` | Qualquer expressão `-k` do pytest |
| `make test-list` | Lista todos os ids de teste |
| `make test-textproc ARGS="-x --lf"` | Flags extras do pytest para qualquer alvo |

```mermaid
flowchart TD
    start(["make test · make test-&lt;name&gt;"]) --> env{".venv existe?"}
    env -- não --> create["python3 -m venv .venv<br/>(registrado)"]
    create --> pyt
    env -- sim --> pyt{"pytest instalado?"}
    pyt -- não --> inst["pip install pytest<br/>(do pyproject [dev], registrado)"]
    pyt -- sim --> route
    inst --> route{"o que rodar"}
    route -- módulo existe --> mod["pytest tests/test_&lt;name&gt;.py"]
    route -- senão --> kw["pytest tests/ -k &lt;name&gt;"]
    route -- make test --> all["pytest tests/ [-k expr]"]
    mod & kw & all --> out(["resultado + 5 testes mais lentos + pulados + tempo"])
```

## 🤝 Contribuindo

PRs são bem-vindos — especialmente no Hacktoberfest! Ideias:

- Diários de locutores (speaker diarization)
- Resumos via LLM (flag opcional)
- Mais formatos de saída (ex.: Anki)
- Melhor suporte a Windows / interface gráfica

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief && ./install.sh
```

Abra uma issue antes de mudanças grandes para alinharmos o escopo.

Veja também: [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md) · [LICENSE](LICENSE)

## 📜 Licença

MIT
