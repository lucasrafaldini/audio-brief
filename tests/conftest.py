"""Shared sample text (English + Portuguese) for offline tests."""

SAMPLE_EN = (
    "Audio brief summarizes meetings. It extracts keywords and builds mind maps. "
    "The tool runs offline with Whisper and needs no API keys. "
    "Transcripts include timestamps for every segment. "
    "Users can export subtitles in SRT and VTT formats. "
    "The command line interface is simple and friendly. "
    "Multiple audio files can be queued and processed in parallel. "
    "Summaries rank the most informative sentences first."
)

SAMPLE_PT = (
    "O audio brief resume reuniões. Ele extrai palavras-chave e cria mapas mentais. "
    "A ferramenta funciona offline com Whisper e não precisa de chaves de API. "
    "As transcrições incluem marcas de tempo para cada segmento. "
    "Os usuários podem exportar legendas nos formatos SRT e VTT. "
    "A interface de linha de comando é simples e amigável."
)

SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 1.5, "text": "Hello world"},
    {"start": 1.5, "end": 61.2, "text": "Second segment here"},
]
