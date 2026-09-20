from pathlib import Path
import tempfile
import threading
import time
import unittest

from diarization import label_segments
from jobs import run_job
from transcription import Segment


def waiting_worker(job, mailbox):
    mailbox.put(("status", "ready"))
    time.sleep(120)


def one_result_worker(job, mailbox):
    mailbox.put(
        (
            "result",
            (0, {"segments": [{"start": 0, "end": 1, "text": "Hello", "speaker": "Speaker 1"}]}),
        )
    )
    mailbox.put(("status", "ready"))
    time.sleep(120)


def failed_worker(job, mailbox):
    import os

    os._exit(7)  # Simulate a native inference crash.


class SpeakerAndJobTests(unittest.TestCase):
    def test_word_alignment_splits_speaker_change(self):
        segments = [
            Segment(
                0, 4, "Hello there. Hi!", words=[(0, 1, "Hello"), (1, 2, " there."), (2, 4, " Hi!")]
            )
        ]
        result = label_segments(segments, [(0, 2, 9), (2, 4, 3)])
        self.assertEqual(
            [(s.speaker, s.text) for s in result],
            [("Speaker 1", "Hello there."), ("Speaker 2", "Hi!")],
        )

    def test_no_overlap_does_not_invent_speaker(self):
        result = label_segments([Segment(10, 11, "Unmatched")], [(0, 1, 7)])
        self.assertEqual(result[0].speaker, "Speaker ?")

    def test_cancel_stops_worker_without_export(self):
        with tempfile.TemporaryDirectory() as folder:
            cancelled, events = threading.Event(), []

            def emit(kind, value):
                events.append((kind, value))
                if kind == "status" and value == "ready":
                    cancelled.set()

            timer = threading.Timer(10, cancelled.set)
            timer.start()
            try:
                run_job(
                    {"files": ["test.wav"], "output": folder, "formats": ["md"]},
                    cancelled,
                    emit,
                    worker=waiting_worker,
                )
            finally:
                timer.cancel()
            self.assertIn(("status", "ready"), events)
            self.assertEqual(events[-1][1], (0, [], ["md"], True))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_cancel_preserves_completed_export(self):
        with tempfile.TemporaryDirectory() as folder:
            cancelled, events = threading.Event(), []
            job = {
                "files": ["test.wav", "next.wav"],
                "output": folder,
                "formats": ["md"],
                "language": "en",
                "timestamps": False,
            }

            def emit(kind, value):
                events.append((kind, value))

            thread = threading.Thread(
                target=run_job, args=(job, cancelled, emit, one_result_worker)
            )
            thread.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not list(Path(folder).glob("*.md")):
                time.sleep(0.05)
            cancelled.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(events[-1][1], (1, [], ["md"], True))
            self.assertIn(
                "Speaker 1: Hello", Path(folder, "test.wav.md").read_text(encoding="utf-8")
            )

    def test_crashed_worker_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            events = []
            run_job(
                {"files": [], "output": folder, "formats": ["md"]},
                threading.Event(),
                lambda kind, value: events.append((kind, value)),
                worker=failed_worker,
            )
            self.assertIn("unexpectedly", events[-1][1][1][0])
