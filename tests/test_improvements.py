import hashlib
import io
import tempfile
import threading
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from diarization import download, label_segments
from jobs import run_job
from settings import DEFAULTS, LANGUAGES, load_settings, save_settings
from transcription import Segment, export, transcribe


def concurrent_export(folder):
    return export("same.wav", folder, [Segment(0, 1, "Hello")], "en", formats=("md", "srt"))


def complete_worker(job, mailbox):
    mailbox.put(
        ("result", (0, {"segments": [{"start": 0, "end": 1, "text": "Bonjour"}], "language": "fr"}))
    )
    mailbox.put(("finished", None))


class ImprovementTests(unittest.TestCase):
    def test_preferences_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            values = dict(DEFAULTS, language="English", srt_output=True)
            save_settings(values, path)
            self.assertEqual(load_settings(path), values)
            path.write_text('{"language": "invalid", "model": [], "timestamps": "false"}')
            self.assertEqual(load_settings(path), DEFAULTS)
            path.write_text("broken")
            self.assertEqual(load_settings(path), DEFAULTS)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_auto_language_reaches_model_and_is_reported(self):
        model = Mock()
        model.transcribe.return_value = (
            iter([Segment(0, 1, "Bonjour")]),
            Mock(duration=1, language="fr"),
        )
        detected = []
        transcribe(model, "file.wav", None, on_language=detected.append)
        self.assertIsNone(model.transcribe.call_args.kwargs["language"])
        self.assertEqual(detected, ["fr"])
        self.assertIn(None, LANGUAGES.values())

    def test_srt_milliseconds_carry_unicode_and_speakers(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = export(
                "file.wav",
                folder,
                [Segment(59.9996, 62.25, "Ol\u00e1", speaker="Speaker 1")],
                "pt",
                formats=("srt",),
            )
            self.assertEqual(
                paths[0].read_text(encoding="utf-8"),
                "1\n00:01:00,000 --> 00:01:02,250\nSpeaker 1: Ol\u00e1\n",
            )

    def test_concurrent_exports_share_stem_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            with ProcessPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(concurrent_export, [folder] * 8))
            self.assertEqual(len({path for pair in results for path in pair}), 16)
            for md, srt in results:
                self.assertEqual(md.stem, srt.stem)
                self.assertIn("Hello", md.read_text())
            self.assertEqual(len(list(Path(folder).iterdir())), 16)

    def test_export_failure_rolls_back_its_files(self):
        import os

        original = os.link

        def fail_second(source, target):
            if target.suffix == ".srt":
                raise OSError("simulated failure")
            original(source, target)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("transcription.os.link", side_effect=fail_second),
        ):
            with self.assertRaises(OSError):
                concurrent_export(folder)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_overlap_index_preserves_long_turns_and_unordered_words(self):
        segments = [Segment(0, 12, "late early", words=[(9, 10, "late"), (0, 1, "early")])]
        result = label_segments(segments, [(0, 12, 0), (3, 4, 1), (8, 8.5, 2)])
        self.assertEqual(result[0].speaker, "Speaker 1")
        self.assertEqual(result[0].text, "late early")
        self.assertEqual(label_segments([], []), [])
        self.assertEqual(label_segments([Segment(0, 1, "Hi")], [])[0].speaker, "Speaker ?")

    def test_download_retries_verifies_and_reuses_cache(self):
        data = b"verified model"
        digest = hashlib.sha256(data).hexdigest()
        response = io.BytesIO(data)
        response.headers = {"Content-Length": str(len(data))}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "model"
            with (
                patch(
                    "diarization.urllib.request.urlopen", side_effect=[OSError("offline"), response]
                ) as request,
                patch("diarization.time.sleep"),
            ):
                download("https://example.invalid/model", target, lambda text: None, digest)
                self.assertEqual(request.call_count, 2)
                download("https://example.invalid/model", target, lambda text: None, digest)
                self.assertEqual(request.call_count, 2)
            self.assertEqual(target.read_bytes(), data)

    def test_invalid_download_is_never_published(self):
        def response(*args, **kwargs):
            value = io.BytesIO(b"corrupt")
            value.headers = {}
            return value

        with (
            tempfile.TemporaryDirectory() as folder,
            patch("diarization.urllib.request.urlopen", side_effect=response),
            patch("diarization.time.sleep"),
        ):
            target = Path(folder) / "model"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                download("https://example.invalid/model", target, lambda text: None, "0" * 64)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_queue_drains_result_and_exports_detected_language(self):
        with tempfile.TemporaryDirectory() as folder:
            events = []
            run_job(
                {
                    "files": ["file.wav"],
                    "output": folder,
                    "formats": ["md"],
                    "language": None,
                    "timestamps": False,
                },
                threading.Event(),
                lambda *event: events.append(event),
                complete_worker,
            )
            self.assertEqual(events[-1][1], (1, [], ["md"], False))
            self.assertIn("Language: fr", Path(folder, "file.wav.md").read_text(encoding="utf-8"))

    def test_already_cancelled_job_does_not_start_worker(self):
        cancelled = threading.Event()
        cancelled.set()
        events = []
        run_job({"formats": ["md"]}, cancelled, lambda *event: events.append(event))
        self.assertEqual(events, [("done", (0, [], ["md"], True))])
