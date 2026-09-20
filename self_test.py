"""Offline smoke check used to validate the packaged Windows application."""
from pathlib import Path
import json
import tempfile
import threading
import time
import traceback


def sleeping_worker(job, mailbox):
    from jobs import write_json
    write_json(Path(mailbox) / "status.json", {"text": "probe-ready"})
    time.sleep(120)


def run(report, job_path=None):
    checks = []
    app = None
    try:
        from app import App
        from jobs import run_job
        from transcription import Segment, export
        import av
        import numpy as np
        import sherpa_onnx
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        from faster_whisper import WhisperModel
        from docx import Document
        assert get_speech_timestamps(np.zeros(16000, dtype=np.float32), VadOptions()) == []
        checks.append("packaged inference imports and VAD model")
        app = App()
        app.withdraw()
        app.update()
        assert app.input_dir.get() == "input_audio"
        assert app.word_output.get() and app.md_output.get()
        checks.append("UI startup")
        app.destroy()
        app = None
        with tempfile.TemporaryDirectory() as folder:
            paths = export("probe.wav", folder, [Segment(0, 1, "Test", speaker="Speaker 1")], "en")
            assert "Speaker 1" in paths[0].read_text(encoding="utf-8")
            assert "Speaker 1" in "\n".join(p.text for p in Document(paths[1]).paragraphs)
            checks.append("Word and Markdown speaker exports")
            cancelled = threading.Event()
            events = []
            def emit(kind, value):
                events.append((kind, value))
                if kind == "status" and value == "probe-ready":
                    cancelled.set()
            job = {"files": [], "output": folder, "formats": ["md"]}
            timer = threading.Timer(20, cancelled.set)
            timer.start()
            try:
                run_job(job, cancelled, emit, worker=sleeping_worker)
            finally:
                timer.cancel()
            assert ("status", "probe-ready") in events
            assert events[-1][0] == "done" and events[-1][1][3]
            assert not events[-1][1][1], events[-1]
            checks.append("spawned worker cancellation")
        if job_path is not None:
            job = json.loads(Path(job_path).read_text(encoding="utf-8"))
            events = []
            run_job(job, threading.Event(), lambda kind, value: events.append((kind, value)))
            completed, errors, _, cancelled = events[-1][1]
            assert not errors and not cancelled and completed == len(job["files"]), events[-1]
            checks.append("full audio transcription and speaker-label integration")
        result = {"ok": True, "checks": checks}
    except Exception:
        result = {"ok": False, "checks": checks, "error": traceback.format_exc()}
    finally:
        if app is not None:
            app.destroy()
    Path(report).write_text(json.dumps(result, indent=2), encoding="utf-8")
