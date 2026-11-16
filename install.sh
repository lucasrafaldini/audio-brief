#!/usr/bin/env bash
# One-shot setup: creates .venv and installs audio-brief into it.
#
#   ./install.sh                          audio-brief + Whisper (pulls PyTorch: ~1-3 GB download)
#   ./install.sh --engine pocketsphinx    audio-brief + PocketSphinx instead (~40 MB, English only)
#   ./install.sh --engine both            both engines (choose per run with --engine)
#   ./install.sh --dev                    ... + pytest, for `make test`
#   ./install.sh --bench                  ... + pytest + benchmark metrics/baselines, for `make bench`
#
#   PYTHON=python3.12 ./install.sh     choose the interpreter (default: python3)
#   NO_COLOR=1 ./install.sh            plain output
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
# shellcheck source=scripts/lib.sh
. scripts/lib.sh

EXTRAS=""
ENGINE=whisper
NEXT_IS_ENGINE=0
for arg in "$@"; do
    if [ "$NEXT_IS_ENGINE" = 1 ]; then ENGINE="$arg"; NEXT_IS_ENGINE=0; continue; fi
    case "$arg" in
        --dev) EXTRAS="${EXTRAS:+$EXTRAS,}dev" ;;
        --bench) EXTRAS="${EXTRAS:+$EXTRAS,}dev,bench" ;;
        --engine=*) ENGINE="${arg#--engine=}" ;;
        --engine) NEXT_IS_ENGINE=1 ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) log_fail "unknown option: $arg (try --help)"; exit 2 ;;
    esac
done

if [ "$NEXT_IS_ENGINE" = 1 ]; then log_fail "--engine needs a value: whisper, pocketsphinx or both"; exit 2; fi
case "$ENGINE" in
    whisper) ENGINE_EXTRAS=whisper ;;
    pocketsphinx) ENGINE_EXTRAS=pocketsphinx ;;
    both) ENGINE_EXTRAS=whisper,pocketsphinx ;;
    *) log_fail "--engine must be whisper, pocketsphinx or both (got: $ENGINE)"; exit 2 ;;
esac
EXTRAS="$ENGINE_EXTRAS${EXTRAS:+,$EXTRAS}"

PYTHON="${PYTHON:-python3}"
VENV=.venv
TOTAL=$SECONDS
STEP="starting"
trap 'log_fail "install.sh stopped during: $STEP (see the messages above)"' ERR

# --- 1. Python ---------------------------------------------------------------
STEP="1/5 checking Python"
log_step "$STEP"
if ! python_ok "$PYTHON"; then
    log_fail "$PYTHON not found or older than 3.10. Install Python 3.10+ (or set PYTHON=/path/to/python3)."
    exit 1
fi
log_info "$("$PYTHON" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
if ! "$PYTHON" -c 'import venv, ensurepip' 2>/dev/null; then
    log_fail "the venv module is missing. On Debian/Ubuntu: sudo apt install python3-venv"
    exit 1
fi
log_ok "Python OK"

# --- 2. virtual environment --------------------------------------------------
STEP="2/5 virtual environment ($VENV)"
log_step "$STEP"
if [ -x "$VENV/bin/python" ]; then
    log_info "reusing existing $VENV ($("$VENV/bin/python" -c 'import sys; print(sys.version.split()[0])'))"
else
    log_cmd "$PYTHON -m venv $VENV"
    "$PYTHON" -m venv "$VENV"
    log_ok "created $VENV"
fi
PY="$VENV/bin/python"

# --- 3. pip ---------------------------------------------------------------
STEP="3/5 upgrading pip"
log_step "$STEP"
start=$SECONDS
log_cmd "$PY -m pip install --upgrade pip"
"$PY" -m pip install --disable-pip-version-check -q --upgrade pip
log_ok "$("$PY" -m pip --version | cut -d' ' -f1-2) ($(since "$start"))"

# --- 4. audio-brief + dependencies -------------------------------------------
TARGET=".[$EXTRAS]"
STEP="4/5 installing audio-brief with extras [$EXTRAS]"
log_step "$STEP"
case ",$EXTRAS," in
    *,whisper,*)
        if "$PY" -c "import torch" 2>/dev/null; then
            log_info "PyTorch already installed: this should be quick."
        else
            log_info "First install downloads openai-whisper and PyTorch (~1-3 GB): this can take several minutes."
        fi ;;
esac
case ",$EXTRAS," in
    *,pocketsphinx,*|*,bench,*)
        log_info "PocketSphinx: prebuilt wheels exist for Python 3.11/3.13; on other versions pip builds it (needs a C compiler and cmake, ~1 min)." ;;
esac
start=$SECONDS
log_cmd "$PY -m pip install -e '$TARGET'"
"$PY" -m pip install --disable-pip-version-check -e "$TARGET"
log_ok "installed in $(since "$start")"

# --- 5. verify -------------------------------------------------------------
STEP="5/5 verifying the installation"
log_step "$STEP"
"$PY" - "$EXTRAS" <<'PYEOF'
import importlib, sys
extras = sys.argv[1].split(",") if sys.argv[1] else []
checks = [("audio_brief", "audio_brief")]
if "whisper" in extras:
    checks += [("openai-whisper", "whisper"), ("torch", "torch")]
if "pocketsphinx" in extras or "bench" in extras:
    checks.append(("pocketsphinx", "pocketsphinx"))
if "dev" in extras:
    checks.append(("pytest", "pytest"))
if "bench" in extras:
    checks += [(n, m) for n, m in [("rouge-score", "rouge_score"), ("segeval", "segeval"), ("yake", "yake"),
                                   ("summa", "summa"), ("sumy", "sumy"), ("scikit-learn", "sklearn"), ("nltk", "nltk"),
                                   ("jiwer", "jiwer")]]
failed = False
for name, module in checks:
    try:
        mod = importlib.import_module(module)
        try:
            from importlib.metadata import version
            ver = getattr(mod, "__version__", None) or version(name)
        except Exception:
            ver = "ok"
        print(f"    {name:15} {ver}")
    except Exception as exc:  # report every broken import, not just the first
        print(f"    {name:15} FAILED: {exc}")
        failed = True
sys.exit(1 if failed else 0)
PYEOF
if command -v ffmpeg >/dev/null 2>&1; then
    log_info "ffmpeg         $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
else
    log_warn "ffmpeg not found: both engines need it to read audio (macOS: brew install ffmpeg, Debian/Ubuntu: sudo apt install ffmpeg)"
fi
log_ok "all packages import"

trap - ERR
echo
log_ok "Setup finished in $(since "$TOTAL"). Environment: $DIR/$VENV ($(du -sh "$VENV" 2>/dev/null | cut -f1))"
log_info "Next:"
log_info "  ./audio-brief doctor                     # check microphone/recording backends"
log_info "  ./audio-brief transcribe your-audio.mp3"
[ -n "$EXTRAS" ] && log_info "  make test                                # run the test suite"
log_info "Tip: export PATH=\"$DIR/$VENV/bin:\$PATH\"   # use 'audio-brief' from anywhere"
