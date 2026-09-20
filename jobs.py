"""Cancellable inference in a child process; only the parent publishes documents."""

from dataclasses import asdict
import multiprocessing
import os
import sys
from pathlib import Path
import queue

from transcription import Segment, export, load_model, transcribe


def inference_worker(job, mailbox):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    def status(text):
        mailbox.put(("status", text))

    def progress(value):
        mailbox.put(("progress", value))

    try:
        status("Cargando modelo / Loading transcription model…")
        model = load_model(job["model"])
        speaker_model = None
        if job["speakers"]:
            from diarization import load_diarizer

            speaker_model = load_diarizer(
                job["speaker_count"], status, job.get("speaker_threshold", 0.5)
            )
        for index, source in enumerate(job["files"]):
            status(f"{index + 1}/{len(job['files'])} — {Path(source).name}")
            try:
                from faster_whisper.audio import decode_audio

                audio = decode_audio(source, sampling_rate=16000)
                from audio import analyze, normalize

                for warning in analyze(audio):
                    mailbox.put(("warning", f"{Path(source).name}: {warning}"))
                audio = normalize(audio)
                detected = []
                segments = transcribe(
                    model,
                    audio,
                    job["language"],
                    progress,
                    word_timestamps=job["speakers"],
                    on_language=detected.append,
                    initial_prompt=job.get("prompt"),
                )
                if speaker_model is not None:
                    from diarization import diarize

                    status("Identificando voces / Identifying speakers…")
                    segments = diarize(speaker_model, audio, segments, progress)
                mailbox.put(
                    (
                        "result",
                        (
                            index,
                            {"segments": [asdict(s) for s in segments], "language": detected[0]},
                        ),
                    )
                )
            except Exception as exc:
                mailbox.put(("result", (index, {"error": str(exc)})))
    except Exception as exc:
        mailbox.put(("fatal", str(exc)))
    finally:
        mailbox.put(("finished", None))


def run_job(job, cancelled, emit, worker=inference_worker):
    """Spawn inference; cancellation never interrupts parent-owned publication."""
    completed, errors = 0, []
    context = multiprocessing.get_context("spawn")
    mailbox = context.Queue(maxsize=64)
    process = context.Process(target=worker, args=(job, mailbox), daemon=True)
    started = False
    finished = False
    try:
        if not cancelled.is_set():
            process.start()
            started = True
        while started and not cancelled.is_set():
            try:
                kind, value = mailbox.get(timeout=0.1)
            except queue.Empty:
                if not process.is_alive():
                    errors.append(f"Audio worker stopped unexpectedly (exit {process.exitcode}).")
                    break
                continue
            if kind == "finished":
                finished = True
                break
            if kind == "fatal":
                errors.append(value)
            elif kind == "result":
                index, result = value
                source = job["files"][index]
                if "error" in result:
                    errors.append(f"{Path(source).name}: {result['error']}")
                elif not cancelled.is_set():
                    try:
                        segments = [Segment(**segment) for segment in result["segments"]]
                        emit("status", "Guardando documentos / Saving documents...")
                        paths = export(
                            source,
                            job["output"],
                            segments,
                            result.get("language", job.get("language")),
                            job["timestamps"],
                            formats=job["formats"],
                        )
                        completed += 1
                        emit("saved", [str(path) for path in paths])
                    except Exception as exc:
                        errors.append(f"{Path(source).name}: {exc}")
            else:
                emit(kind, value)
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if started:
            if finished:
                process.join(timeout=5)
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
        process.close()
        mailbox.close()
        mailbox.join_thread()
        emit("done", (completed, errors, job["formats"], cancelled.is_set()))
