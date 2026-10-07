# CLAUDE.md

See [AGENTS.md](AGENTS.md) for the full project guide (architecture,
conventions, setup, testing). This file exists so Claude Code picks up the
same instructions automatically.

Quick rules:

- Setup: `./install.sh`, then `./audio-brief --help`
- Verify changes: `python3 -m py_compile audio_brief/*.py`
- Keep docs trilingual (`README.md`, `README.pt-BR.md`, `README.es.md`)
- Never commit generated runs or audio files
