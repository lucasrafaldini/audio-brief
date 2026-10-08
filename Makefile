.PHONY: setup test lint clean doctor

setup:
	./install.sh

test:
	python3 -m pytest tests/ -q

lint:
	python3 -m py_compile audio_brief/*.py

clean:
	rm -rf audio-brief-*/ .pytest_cache **/__pycache__

doctor:
	./audio-brief doctor
