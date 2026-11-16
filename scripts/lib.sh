# Shared logging helpers for install.sh and the Makefile (source this file).
# Portable to macOS bash 3.2: no associative arrays, timing via $SECONDS.
# Set NO_COLOR=1 to disable colours (they are off automatically when piped).

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    _B=$'\033[1m'; _G=$'\033[32m'; _R=$'\033[31m'; _Y=$'\033[33m'; _D=$'\033[2m'; _N=$'\033[0m'
else
    _B=""; _G=""; _R=""; _Y=""; _D=""; _N=""
fi

log_step() { printf '%s==> [%s] %s%s\n' "$_B" "$(date +%H:%M:%S)" "$*" "$_N"; }
log_info() { printf '    %s\n' "$*"; }
log_cmd()  { printf '    %s$ %s%s\n' "$_D" "$*" "$_N"; }
log_ok()   { printf '%s ✔  %s%s\n' "$_G" "$*" "$_N"; }
log_warn() { printf '%s !  %s%s\n' "$_Y" "$*" "$_N" >&2; }
log_fail() { printf '%s ✘  %s%s\n' "$_R" "$*" "$_N" >&2; }

# human duration since a $SECONDS snapshot: "<1s", "42s", "3m05s"
since() {
    local d=$((SECONDS - $1))
    if [ "$d" -lt 1 ]; then printf '<1s'
    elif [ "$d" -lt 60 ]; then printf '%ds' "$d"
    else printf '%dm%02ds' $((d / 60)) $((d % 60)); fi
}

# python_ok PY -> 0 if PY exists and is Python >= 3.10
python_ok() {
    command -v "$1" >/dev/null 2>&1 && "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null
}
