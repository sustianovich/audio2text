"""Cancellable inference in a child process; only the parent publishes documents."""
from dataclasses import asdict
import json
import multiprocessing
import os
import sys
from pathlib import Path
import tempfile
import time

from transcription import Segment, export, load_model, transcribe


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    for attempt in range(20):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)


def inference_worker(job, mailbox):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    mailbox = Path(mailbox)
    def status(text):
        write_json(mailbox / "status.json", {"text": text})
    def progress(value):
        write_json(mailbox / "status.json", {"progress": value})
    try:
        status("Cargando modelo / Loading transcription model…")
        model = load_model(job["model"])
        speaker_model = None
        if job["speakers"]:
            from diarization import load_diarizer
            speaker_model = load_diarizer(job["speaker_count"], status)
        for index, source in enumerate(job["files"]):
            status(f'{index + 1}/{len(job["files"])} — {Path(source).name}')
            try:
                from faster_whisper.audio import decode_audio
                audio = decode_audio(source, sampling_rate=16000)
                segments = transcribe(model, audio, job["language"], progress,
                                      word_timestamps=job["speakers"])
                if speaker_model is not None:
                    from diarization import diarize
                    status("Identificando voces / Identifying speakers…")
                    segments = diarize(speaker_model, audio, segments, progress)
                write_json(mailbox / f"{index}.json", {"segments": [asdict(s) for s in segments]})
            except Exception as exc:
                write_json(mailbox / f"{index}.json", {"error": str(exc)})
    except Exception as exc:
        write_json(mailbox / "fatal.json", {"error": str(exc)})
    finally:
        write_json(mailbox / "done.json", {})


def run_job(job, cancelled, emit, worker=inference_worker):
    """Kill inference promptly on cancel, but never interrupt document publication."""
    completed, errors = 0, []
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="audio2text-") as mailbox:
            folder = Path(mailbox)
            process = multiprocessing.get_context("spawn").Process(
                target=worker, args=(job, mailbox), daemon=True)
            process.start()
            next_result, last_status = 0, None
            try:
                while True:
                    if cancelled.is_set():
                        break
                    status_file = folder / "status.json"
                    if status_file.exists():
                        try:
                            value = json.loads(status_file.read_text(encoding="utf-8"))
                            if value != last_status:
                                emit("status" if "text" in value else "progress",
                                     value.get("text", value.get("progress")))
                                last_status = value
                        except (OSError, ValueError):
                            pass  # Atomic writer may have replaced it during this read.
                    result_file = folder / f"{next_result}.json"
                    if result_file.exists() and next_result < len(job["files"]):
                        result = json.loads(result_file.read_text(encoding="utf-8"))
                        source = job["files"][next_result]
                        if "error" in result:
                            errors.append(f'{Path(source).name}: {result["error"]}')
                        else:
                            segments = [Segment(**segment) for segment in result["segments"]]
                            if cancelled.is_set():
                                break
                            emit("status", "Guardando documentos / Saving documents…")
                            try:
                                export(source, job["output"], segments, job["language"],
                                       job["timestamps"], formats=job["formats"])
                                completed += 1
                            except Exception as exc:
                                errors.append(f"{Path(source).name}: {exc}")
                        next_result += 1
                        continue
                    if not process.is_alive():
                        # Drain all completed file results before finishing.
                        if (folder / f"{next_result}.json").exists():
                            continue
                        if (folder / "fatal.json").exists():
                            errors.append(json.loads((folder / "fatal.json").read_text(encoding="utf-8"))["error"])
                        elif not (folder / "done.json").exists():
                            errors.append(f"Audio worker stopped unexpectedly (exit {process.exitcode}).")
                        break
                    time.sleep(0.1)
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()
    except Exception as exc:
        errors.append(str(exc))
    finally:
        emit("done", (completed, errors, job["formats"], cancelled.is_set()))
