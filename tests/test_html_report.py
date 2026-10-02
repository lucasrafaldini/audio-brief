import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from audio_brief import cli, writers


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


class HtmlReportTests(unittest.TestCase):
    def test_all_sections_and_unicode_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            writers.write_report_html(
                "Complete transcript.\nİstanbul café.", [("coffee", 3)],
                ["A useful summary."], "# Audio mindmap\n## coffee", path,
                {"source": "lecture.wav", "duration": 65, "generated": "2026-10-02"},
            )
            parser = ReportParser()
            parser.feed(path.read_text(encoding="utf-8"))
            rendered = "".join(parser.text)
            for expected in ("Complete transcript.", "İstanbul café.", "coffee",
                             "A useful summary.", "# Audio mindmap", "0:01:05", "2026-10-02"):
                self.assertIn(expected, rendered)
            for section in ("summary", "keywords", "mindmap", "transcript"):
                self.assertIn(("id", section), parser.attributes)
                self.assertIn(("href", f"#{section}"), parser.attributes)
            self.assertNotIn("script", parser.tags)
            self.assertNotIn("link", parser.tags)

    def test_dynamic_content_is_text_not_markup(self):
        text = '<script>quoted & "content"</script>'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            writers.write_report_html(text, [(text, 1)], [text], text, path, {"source": text})
            parser = ReportParser()
            parser.feed(path.read_text(encoding="utf-8"))
            self.assertNotIn("script", parser.tags)
            self.assertGreaterEqual("".join(parser.text).count(text), 5)

    def test_empty_report_is_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.html"
            writers.write_report_html("", [], [], "", path, {})
            content = path.read_text(encoding="utf-8")
            self.assertIn("No keywords could be extracted.", content)
            self.assertIn("No summary could be extracted.", content)
            self.assertIn("0:00:00", content)

    def test_transcription_writes_html_alongside_existing_outputs(self):
        result = {"text": "Coffee tastes wonderful. Coffee helps us focus.",
                  "segments": [], "language": "en", "duration": 5}
        model = SimpleNamespace(transcribe=lambda *args, **kwargs: result)
        whisper = SimpleNamespace(load_model=lambda name: model)
        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules", {"whisper": whisper}):
            output = Path(directory)
            cli.transcribe_and_write("lecture.wav", "base", "en", output)
            self.assertTrue((output / "report.md").is_file())
            self.assertIn(result["text"], (output / "report.html").read_text(encoding="utf-8"))
            self.assertTrue((output / "transcript.json").is_file())


if __name__ == "__main__":
    unittest.main()
