#!/usr/bin/env bash
# Run a command as a logged, timed step:  scripts/run.sh "label" cmd args...
set -uo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"
label=$1; shift
log_step "$label"
log_cmd "$*"
start=$SECONDS
"$@"
rc=$?
if [ "$rc" -eq 0 ]; then
    log_ok "$label: done in $(since "$start")"
else
    log_fail "$label: failed (exit $rc) after $(since "$start")"
fi
exit "$rc"
