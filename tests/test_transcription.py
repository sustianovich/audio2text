import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from docx import Document
from transcription import Segment, discover, export, transcribe


class TranscriptionTests(unittest.TestCase):
    def test_discover_filters_media(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ["audio.M4V", "sound.m4a", "notes.md"]:
                Path(folder, name).touch()
            self.assertEqual([p.name for p in discover(folder)], ["audio.M4V", "sound.m4a"])

    def test_both_exports_unicode_timestamps_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            segments = [Segment(65, 70, "Hola, ¿cómo estás?")]
            md, docx = export("audio.m4a", folder, segments, "es", True)
            self.assertIn("[00:01:05 – 00:01:10] Hola, ¿cómo estás?", md.read_text(encoding="utf-8"))
            self.assertIn("Hola, ¿cómo estás?", "\n".join(p.text for p in Document(docx).paragraphs))
            second = export("audio.m4a", folder, segments, "en")
            self.assertNotEqual(md, second[0])
            self.assertTrue(md.exists() and docx.exists())

    def test_transcription_language_progress_and_silence(self):
        model = Mock()
        model.transcribe.return_value = (iter([Segment(0, 2, " Hello ")]), Mock(duration=2))
        progress = []
        result = transcribe(model, "audio.m4v", "en", progress.append)
        self.assertEqual(result[0].text, "Hello")
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "en")
        self.assertEqual(progress[-1], 100)
        model.transcribe.return_value = (iter([]), Mock(duration=2))
        with self.assertRaisesRegex(ValueError, "No speech"):
            transcribe(model, "audio.m4v", "es")


if __name__ == "__main__":
    unittest.main()
