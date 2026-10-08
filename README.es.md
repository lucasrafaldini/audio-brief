# 🎧 audio-brief

> 🌐 [English](README.md) · [Português (Brasil)](README.pt-BR.md) · **Español**

[![Hacktoberfest](https://img.shields.io/badge/Hacktoberfest-2026-f74700?style=flat-square)](https://hacktoberfest.com)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

Graba o transcribe audio con **OpenAI Whisper** y obtén automáticamente un
**resumen**, un **mapa mental**, **palabras clave** y transcripciones listas
(`.txt`, `.srt`, `.vtt`, `.json`) — todo en un solo comando. Sin claves de API,
funciona offline (tras la primera descarga del modelo).

Funciona en **Linux** y **macOS**.

## ✨ Características

- 🎙️ Graba desde el micrófono o transcribe archivos de audio existentes
- 🌍 Detección automática de idioma (o fuerza con `--language`)
- 🧠 Resumen extractivo, extracción de palabras clave y mapas mentales (Markmap + Mermaid)
- 📄 Subtítulos en SRT/VTT + `report.md` y `report.html` todo-en-uno
- 🩺 El comando `doctor` revisa tu entorno (Whisper, ffmpeg, micrófono)
- ⚡ Cola de múltiples archivos, opcionalmente en paralelo con `--jobs N`
- 🖥️ CLI amigable: valores por defecto sensatos, sin preguntas en pipe/CI

## 🚀 Inicio rápido

Requiere **Python 3.10+** y (para grabar en macOS) `ffmpeg`
(`brew install ffmpeg` en macOS, `apt install ffmpeg` en Debian/Ubuntu).

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief
./install.sh          # crea .venv e instala todo
```

Luego:

```bash
./audio-brief transcribe reunion.mp3        # elige modelo/idioma interactivamente
./audio-brief transcribe reunion.mp3 --model base --language es
./audio-brief record 120                     # graba 2 minutos, luego transcribe
```

Tras `install.sh`, también puedes añadir el venv al PATH y usar el comando
directamente:

```bash
export PATH="$PWD/.venv/bin:$PATH"
audio-brief --help
```

### Otras formas de instalar

```bash
pip install .          # en el entorno actual
pipx install .         # instalación aislada del CLI
```

## 📖 Uso

```
audio-brief record [segundos] [--model M] [--language L] [--out DIR] [--keep-raw]
audio-brief transcribe <archivo> [archivo2 ...] [--jobs N] [--model M] [--language L] [--out DIR]
audio-brief doctor
audio-brief --version
```

| Opción | Significado |
|--------|---------|
| `--model` | `tiny` (rápido/impreciso) → `base` → `small` → `medium` → `large`/`turbo` (preciso, más lento) |
| `--language` | Código ISO de 2–3 letras (p. ej. `en`, `pt`, `es`). Salta la pregunta; detecta automático si no se define |
| `--out DIR` | Elige el directorio de salida |
| `--jobs N` | Transcribe N archivos en paralelo |
| `--summary-n N` | Máximo de frases en el resumen (por defecto: 8) |
| `--keywords-n N` | Máximo de palabras clave extraídas (por defecto: 15) |
| `--keep-raw` | Conserva el `.wav` grabado dentro de la carpeta de salida (solo `record`) |

Ejecuta `audio-brief doctor` primero si algo no funciona — revisa
Python, Whisper, backends de grabación y (en macOS) lista los dispositivos de audio.

Ejemplos:

```bash
# un archivo, inglés, modelo medium
audio-brief transcribe clase.wav --model medium --language en

# tres archivos, dos a la vez
audio-brief transcribe a.mp3 b.mp3 c.mp3 --jobs 2
```

Al ejecutarse interactivamente se te preguntará por idioma y modelo una vez;
al usarse en pipe (CI, scripts) usa auto-detección + `base`.

## 📂 Salidas

Los archivos se guardan en `audio-brief-<timestamp>/` junto al audio (o en el
directorio actual para grabaciones):

| Archivo | Contenido |
|------|---------|
| `transcript.txt` | Transcripción de texto con marcas de tiempo |
| `transcript.srt` / `.vtt` | Subtítulos |
| `transcript.json` | Datos brutos de los segmentos |
| `summary.md` | Frases clave, ordenadas por relevancia |
| `keywords.md` | Temas/palabras clave con frecuencias |
| `mindmap.md` | Mapa mental (pega en [markmap.js.org](https://markmap.js.org)) |
| `mindmap.mmd` | Mapa mental en Mermaid ([mermaid.live](https://mermaid.live)) |
| `report.md` | Todo en un único Markdown |
| `report.html` | Mismo informe como página web autocontenida (sin visor necesario) |

## ⚙️ Backends de grabación

Se elige automáticamente: `arecord` (Linux/ALSA) → `ffmpeg` (macOS vía
avfoundation, Linux vía ALSA) → `sox rec`. Forza uno y elige el micrófono:

```bash
AUDIO_BRIEF_RECORDER=ffmpeg AUDIO_BRIEF_MIC=1 audio-brief record 60
# listar entradas de audio en macOS:
ffmpeg -f avfoundation -list_devices true -i ''
```

## 💡 Tamaño de los modelos

| Modelo | Tamaño | Velocidad (CPU) | Calidad |
|-------|------|-------------|---------|
| `tiny` | ~75 MB | más rápido | impreciso |
| `base` | ~150 MB | rápido | ok para un brief |
| `small` | ~500 MB | medio | bueno |
| `medium` | ~1,5 GB | lento | muy bueno |
| `large`/`turbo` | ~3 GB | más lento | mejor |

## 🍎 App macOS (opcional)

```bash
.venv/bin/pip install py2app
.venv/bin/python setup.py py2app -A
# -> dist/audio-brief.app
```

## 🤝 Contribuir

¡Los PRs son bienvenidos — especialmente en Hacktoberfest! Ideas:

- Diarización de hablantes
- Resúmenes con LLM (flag opcional)
- Más formatos de salida (HTML, Obsidian, Anki)
- Mejor soporte para Windows / interfaz gráfica

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief && ./install.sh
```

Abre un issue antes de cambios grandes para alinear el alcance.

Ver también: [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md) · [LICENSE](LICENSE)

## 📜 Licencia

MIT
