# Contributing to audio-brief

Thanks for your interest! This project is 100% open source and welcomes
contributions of all sizes — bug fixes, features, docs, or ideas.

## How to contribute

1. Fork the repo and create a branch: `git checkout -b my-feature`
2. Set up your environment:
   ```bash
   ./install.sh
   ```
3. Make your changes. Keep the code style consistent with the existing code
   (type hints, docstrings, no new heavy dependencies without discussion).
4. Test your change: `./audio-brief --help`, `python3 -m py_compile audio_brief/*.py`,
   and a real transcribe if you touched the pipeline.
5. Open a Pull Request. Link the related issue if there is one.

## Good first issues

Check issues labeled
[`good first issue`](https://github.com/lucasrafaldini/audio-brief/labels/good%20first%20issue).
Comment on one before starting so we can assign it to you.

## Reporting bugs

Open an issue with: your OS, Python version, the command you ran, and the
full error output.

## License

By contributing, you agree that your contributions are licensed under the
MIT License.
