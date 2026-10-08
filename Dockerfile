FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY audio_brief ./audio_brief
RUN pip install --no-cache-dir openai-whisper && pip install --no-cache-dir -e . --no-deps

ENTRYPOINT ["audio-brief"]
CMD ["--help"]
