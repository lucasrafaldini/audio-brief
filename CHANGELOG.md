# Changelog

## [0.3.0] — Unreleased

### Added

- `report.html`: self-contained HTML report (inline CSS, no external assets)
- `audio-brief doctor`: environment check (Python, Whisper, recording backends, macOS devices)
- `--summary-n` / `--keywords-n`: control summary and keyword length
- `recorder.backend_status()` and `recorder.list_devices()`
- `textproc.stats()`: word/sentence counts and reading time in reports
- Test suite (`tests/`, pytest) with CI on Linux + macOS, Python 3.10–3.12
- `Makefile`, `Dockerfile`, Claude skill (`.claude/skills/audio-brief/`)

### Fixed

- VTT timestamps now use `.` (period) instead of SRT-style `,` — valid WebVTT
- `_hms()` always zero-padded (`00:00:05` instead of `0:00:05`)
- Whisper model loads once and is reused across files (was: reload per file)
- Summary/keywords computed once per file (was: computed twice)
- `record` validates duration; parallel failures now set exit code 1

### Changed

- Portuguese stopwords added to `textproc` (docs are trilingual)
- `transcribe_and_write()` returns the output path; `main()` returns exit codes

## [0.2.0]

- Hacktoberfest-ready: cleanup, `install.sh`, `pyproject.toml`, new README
- Fixed `record` subcommand (`--keep-raw`/`--model`/`--language`/`--out`)
- Non-interactive fallback (base model + auto-detect)

## [0.1.0]

- Initial release: record/transcribe with Whisper, summaries, mindmaps
