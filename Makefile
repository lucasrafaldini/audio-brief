SHELL := bash
.DEFAULT_GOAL := help
.PHONY: help setup setup-light test-env test test-list bench-env bench-data bench bench-quick lint clean doctor

VENV ?= .venv
# PYTHON=/path/to/python uses another interpreter (checked, never modified);
# by default everything runs in the project venv, created on demand.
PY := $(if $(PYTHON),$(PYTHON),$(VENV)/bin/python)
RUN := scripts/run.sh
# Extra flags for pytest / the benchmark, e.g. make test ARGS="-x --lf"
ARGS ?=
# Optional pytest -k expression, e.g. make test K="obsidian and not empty"
K ?=
PYTEST := $(PY) -m pytest -q -ra --durations=5
TEST_MODULES = $(patsubst tests/test_%.py,%,$(wildcard tests/test_*.py))

help:
	@echo "Setup"
	@echo "  make setup              full install into $(VENV): app + Whisper/PyTorch + pytest (logs every step)"
	@echo "  make setup-light        app + PocketSphinx (no PyTorch, ~40 MB, English only) + pytest"
	@echo "Tests (create a light $(VENV) with pytest on first run; Whisper is not needed)"
	@echo "  make test               whole suite, with the 5 slowest tests and a timing summary"
	@echo "  make test K=\"expr\"      tests matching a pytest -k expression"
	@echo "  make test-<module>      one module: $(TEST_MODULES)"
	@echo "  make test-<keyword>     tests whose name contains <keyword>, e.g. make test-obsidian"
	@echo "  make test-list          list every test id"
	@echo "Benchmarks (see benchmarks/METHODOLOGY.md)"
	@echo "  make bench-data         download the pinned, checksummed public corpora (~30 MB)"
	@echo "  make bench              full benchmark -> benchmarks/RESULTS.md + results.json (~15 min)"
	@echo "  make bench-quick        small run on every dataset (a few min), printed, RESULTS.md untouched"
	@echo "Other"
	@echo "  make lint | clean | doctor"
	@echo "Options: ARGS=\"...\" (extra flags), PYTHON=... (interpreter: $(PY)), NO_COLOR=1"

setup:
	@bash ./install.sh --dev

setup-light:
	@bash ./install.sh --dev --engine pocketsphinx

test-env:
	@scripts/ensure-venv.sh "$(PY)" "$(VENV)" test

test: test-env
	@$(RUN) "test suite$(if $(K), (-k '$(K)'))" $(PYTEST) tests/ $(if $(K),-k "$(K)") $(ARGS)

test-list: test-env
	@$(PY) -m pytest tests/ --collect-only -q $(ARGS) | grep '::'

# make test-writers    -> tests/test_writers.py
# make test-group-chat -> tests/test_group_chat.py (hyphens become underscores)
# make test-obsidian   -> no such module, so: pytest -k obsidian across the suite
test-%: test-env
	@ctx="$(subst -,_,$*)"; \
	if [ -f "tests/test_$$ctx.py" ]; then \
		$(RUN) "tests in tests/test_$$ctx.py" $(PYTEST) "tests/test_$$ctx.py" $(ARGS); \
	else \
		$(RUN) "tests matching '$$ctx'" $(PYTEST) tests/ -k "$$ctx" $(ARGS); \
	fi

bench-env:
	@scripts/ensure-venv.sh "$(PY)" "$(VENV)" bench

bench-data: bench-env
	@$(RUN) "benchmark data (pinned + checksummed)" $(PY) -m benchmarks.fetch_data

bench: bench-data
	@$(RUN) "benchmarks (full)" $(PY) -m benchmarks.run $(ARGS)

bench-quick: bench-data
	@dir=$$(mktemp -d); $(RUN) "benchmarks (quick)" $(PY) -m benchmarks.run --quick --out "$$dir/RESULTS.md" $(ARGS) \
		&& cat "$$dir/RESULTS.md"; rc=$$?; rm -rf "$$dir"; exit $$rc

lint:
	@$(RUN) "lint (byte-compile + shell syntax)" bash -c \
		'python3 -m py_compile audio_brief/*.py benchmarks/*.py && for f in install.sh audio-brief scripts/*.sh; do bash -n "$$f"; done'

clean:
	rm -rf audio-brief-*/ .pytest_cache **/__pycache__

doctor:
	@$(RUN) "doctor" ./audio-brief doctor
