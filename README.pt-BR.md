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
- 📄 Legendas em SRT/VTT + um `report.md` tudo-em-um
- ⚡ Fila de múltiplos arquivos, opcionalmente em paralelo com `--jobs N`
- 🖥️ CLI amigável: padrões sensatos, zero perguntas quando usado em pipe/CI

## 🚀 Início rápido

Requer **Python 3.10+** e (para gravar no macOS) `ffmpeg`
(`brew install ffmpeg` no macOS, `apt install ffmpeg` no Debian/Ubuntu).

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief
./install.sh          # cria .venv e instala tudo
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
pip install .          # no ambiente atual
pipx install .         # instalação isolada do CLI
```

## 📖 Uso

```
audio-brief record [segundos] [--model M] [--language L] [--out DIR] [--keep-raw]
audio-brief transcribe <arquivo> [arquivo2 ...] [--jobs N] [--model M] [--language L] [--out DIR]
audio-brief --version
```

| Opção | Significado |
|--------|---------|
| `--model` | `tiny` (rápido/impreciso) → `base` → `small` → `medium` → `large`/`turbo` (preciso, mais lento) |
| `--language` | Código ISO de 2–3 letras (ex.: `en`, `pt`, `es`). Pula a pergunta; detecta automático se não definido |
| `--out DIR` | Escolhe o diretório de saída |
| `--jobs N` | Transcreve N arquivos em paralelo |
| `--keep-raw` | Mantém o `.wav` gravado dentro da pasta de saída (só `record`) |

Exemplos:

```bash
# um arquivo, inglês, modelo medium
audio-brief transcribe aula.wav --model medium --language en

# três arquivos, dois por vez
audio-brief transcribe a.mp3 b.mp3 c.mp3 --jobs 2
```

Quando executado interativamente, você será perguntado sobre idioma e modelo
uma vez; quando usado em pipe (CI, scripts), usa auto-detect + `base`.

## 📂 Saídas

Os arquivos caem em `audio-brief-<timestamp>/` ao lado do áudio (ou no diretório
atual para gravações):

| Arquivo | Conteúdo |
|------|---------|
| `transcript.txt` | Transcrição em texto com timestamps |
| `transcript.srt` / `.vtt` | Legendas |
| `transcript.json` | Dados brutos dos segmentos |
| `summary.md` | Frases-chave, ranqueadas |
| `keywords.md` | Tópicos/palavras-chave com frequências |
| `mindmap.md` | Mapa mental (cole em [markmap.js.org](https://markmap.js.org)) |
| `mindmap.mmd` | Mapa mental em Mermaid ([mermaid.live](https://mermaid.live)) |
| `report.md` | Tudo em um único Markdown |

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

## 🍎 App macOS (opcional)

```bash
.venv/bin/pip install py2app
.venv/bin/python setup.py py2app -A
# -> dist/audio-brief.app
```

## 🤝 Contribuindo

PRs são bem-vindos — especialmente no Hacktoberfest! Ideias:

- Diários de locutores (speaker diarization)
- Resumos via LLM (flag opcional)
- Mais formatos de saída (HTML, Obsidian, Anki)
- Melhor suporte a Windows / interface gráfica

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief && ./install.sh
```

Abra uma issue antes de mudanças grandes para alinharmos o escopo.

Veja também: [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md) · [LICENSE](LICENSE)

## 📜 Licença

MIT
