#!/usr/bin/env bash
# Make sure an interpreter can run the requested tool set, without ever
# installing into the system Python (PEP 668 forbids that on modern distros).
#
#   scripts/ensure-venv.sh PY VENV test    -> pytest available
#   scripts/ensure-venv.sh PY VENV bench   -> pytest + benchmark extras
#
# PY is either VENV/bin/python (managed here: created/updated as needed) or an
# interpreter chosen by the user with PYTHON=... (only checked, never modified).
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=lib.sh
. scripts/lib.sh
PY=$1; VENV=$2; WHAT=$3
managed=0; [ "$PY" = "$VENV/bin/python" ] && managed=1

if [ "$managed" = 1 ] && [ ! -x "$PY" ]; then
    BOOT=${BOOTSTRAP_PYTHON:-python3}
    log_step "No $VENV yet: creating a lightweight environment for $WHAT"
    if ! python_ok "$BOOT"; then
        log_fail "$BOOT (Python >= 3.10) not found. Install Python 3.10+ or set BOOTSTRAP_PYTHON=/path/to/python3."
        exit 1
    fi
    log_cmd "$BOOT -m venv $VENV"
    if ! "$BOOT" -m venv "$VENV"; then
        log_fail "Could not create $VENV. On Debian/Ubuntu: sudo apt install python3-venv"
        exit 1
    fi
    log_ok "created $VENV with $("$PY" -c 'import sys; print(sys.version.split()[0])')"
    log_info "(Whisper is NOT installed by this step; run 'make setup' for the full app.)"
fi

need=(pytest)
[ "$WHAT" = bench ] && need+=(rouge_score segeval yake summa sumy sklearn nltk pocketsphinx jiwer)
missing=()
for mod in "${need[@]}"; do "$PY" -c "import $mod" 2>/dev/null || missing+=("$mod"); done

if [ "${#missing[@]}" -gt 0 ]; then
    extra=dev; [ "$WHAT" = bench ] && extra="dev,bench"
    if [ "$managed" = 0 ]; then
        log_fail "$PY is missing: ${missing[*]}."
        log_info "Either unset PYTHON to use the project venv ($VENV), or inside a virtualenv run:"
        log_info "  $PY -m pip install -e '.[$extra]'"
        exit 1
    fi
    log_step "Installing missing $WHAT dependencies into $VENV: ${missing[*]}"
    log_info "from pyproject.toml optional-dependencies [$extra]; Whisper/PyTorch are not needed for this"
    start=$SECONDS
    log_cmd "$PY -m pip install --no-deps -e ."
    "$PY" -m pip install --disable-pip-version-check -q --no-deps -e .
    # extras without the package's own runtime deps (openai-whisper/torch)
    reqs=$("$PY" - "$extra" <<'PYEOF'
import re, sys
extras = sys.argv[1].split(",")
try:
    import tomllib  # Python >= 3.11
    opt = tomllib.load(open("pyproject.toml", "rb"))["project"]["optional-dependencies"]
except ImportError:  # Python 3.10: extras are single-line lists in pyproject.toml
    text = open("pyproject.toml", encoding="utf-8").read()
    section = text.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
    opt = {m.group(1): re.findall(r'"([^"]+)"', m.group(2))
           for m in re.finditer(r"^([\w-]+)\s*=\s*\[(.*)\]\s*$", section, re.M)}
print("\n".join(r for e in extras for r in opt[e]))
PYEOF
)
    # shellcheck disable=SC2086
    log_cmd "$PY -m pip install $(echo $reqs)"
    # shellcheck disable=SC2086
    "$PY" -m pip install --disable-pip-version-check $reqs
    log_ok "installed in $(since "$start")"
fi

log_info "python : $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
log_info "pytest : $("$PY" -m pytest --version 2>&1 | head -1)"
if "$PY" -c "import whisper" 2>/dev/null; then
    log_info "whisper: installed (tests stub it anyway)"
else
    log_info "whisper: not installed (not needed: tests stub it)"
fi
