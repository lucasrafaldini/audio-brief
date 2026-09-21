"""py2app configuration for audio-brief macOS app bundle.

Run on macOS: python3 setup.py py2app -A

This will produce a self-contained app bundle in dist/audio-brief.app
that includes the Python runtime and all pure Python dependencies.

Note: Whisper model files (tiny/base/etc.) are downloaded on first run
from OpenAI's servers. Ensure network access on first launch, or bundle
a model manually if desired.
"""

from setuptools import setup

APP = ["audio_brief/cli.py"]
# The shell wrapper script that the project already provides:
#   ~/Desktop/audio-brief/audio-brief
# Py2app will bundle the Python interpreter and required modules only.
# We point to the CLI module directly.

DATA_FILES = []

OPTIONS = {
    "argv_emulation": True,   # allows the app to accept CLI args via open dialog
    "plist": {
        "CFBundleName": "audio-brief",
        "CFBundleDisplayName": "audio-brief",
        "CFBundleVersion": "0.1.0",
        "CFBundleIdentifier": "com.audiobrief.app",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": False,
    },
    "includes": [
        "whisper", "numpy", "torch", "json", "re", "datetime", "pathlib",
        "collections", "subprocess", "tempfile", "shutil", "ffi",
    ],
    "packages": [
        "whisper", "numpy", "torch", "tqdm", "tokenizers", "llvmlite",
        "mpmath", "markupsafe", "more-itertools", "numba", "triton",
    ],
    "optimize": 1,
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)