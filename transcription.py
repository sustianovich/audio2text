"""Local media transcription and paired document export."""
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

SUPPORTED = {".m4v", ".m4a", ".mp4", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".webm", ".mov", ".wma"}
ROOT = Path(__file__).resolve().parent


@dataclass
class Segment:
    start: float
    end: float
    text: str


def discover(folder):
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("La carpeta de entrada no existe.")
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED),
                  key=lambda p: p.name.casefold())


def timestamp(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def export(source, output, segments, language, timestamps=False, formats=("md", "docx")):
    formats = tuple(dict.fromkeys(formats))
    if not formats or any(fmt not in {"md", "docx"} for fmt in formats):
        raise ValueError("Select at least one valid output format: md, docx.")
    # Keep output ordering stable for callers.
    extensions = tuple("." + fmt for fmt in ("md", "docx") if fmt in formats)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Include the source extension so similarly named audio/video files stay distinct.
    stem = Path(source).name
    candidate = stem
    index = 2
    while any((output / f"{candidate}{ext}").exists() for ext in extensions):
        candidate = f"{stem} ({index})"
        index += 1
    targets = tuple(output / f"{candidate}{ext}" for ext in extensions)
    title = Path(source).name
    language_name = {"es": "Español", "en": "English"}[language]
    document = None
    if "docx" in formats:
        from docx import Document
        document = Document()
        document.add_heading(title, 0)
        document.add_paragraph(f"Idioma / Language: {language_name}")
    lines = [f"# {title}", "", f"Idioma / Language: {language_name}", ""]
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if timestamps:
            text = f"[{timestamp(segment.start)} – {timestamp(segment.end)}] {text}"
        lines.extend([text, ""])
        if document is not None:
            document.add_paragraph(text)
    temporary = []
    published = []
    try:
        for suffix in extensions:
            fd, name = tempfile.mkstemp(dir=output, suffix=suffix)
            os.close(fd)
            temporary.append(Path(name))
        for temp, suffix in zip(temporary, extensions):
            if suffix == ".md":
                temp.write_text("\n".join(lines), encoding="utf-8")
            else:
                document.save(str(temp))
        for temp, target in zip(temporary, targets):
            # Exclusive creation also prevents overwriting a file from another run.
            with target.open("xb") as handle:
                published.append(target)
                handle.write(temp.read_bytes())
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return targets


def load_model(name):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cpu", compute_type="int8",
                        download_root=str(ROOT / ".models"))


def transcribe(model, source, language, on_progress=lambda value: None):
    segments, info = model.transcribe(str(source), language=language, task="transcribe",
                                     beam_size=5, vad_filter=True)
    result = []
    for segment in segments:
        if segment.text.strip():
            result.append(Segment(segment.start, segment.end, segment.text.strip()))
        on_progress(min(100, segment.end / max(info.duration, 1) * 100))
    if not result:
        raise ValueError("No se ha detectado voz / No speech detected.")
    on_progress(100)
    return result
