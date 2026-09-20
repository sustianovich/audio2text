"""Local speaker turns and word-level alignment using sherpa-onnx."""
from pathlib import Path
import shutil
import tarfile
import urllib.request
import uuid

from paths import MODEL_DIR
from transcription import Segment

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = RELEASES + "/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_URL = RELEASES + "/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"


def download(url, destination, status):
    """Publish a complete download only; interrupted files are never loaded."""
    destination = Path(destination)
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".part")
    try:
        status("Descargando modelo de voces / Downloading speaker model…")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_diarizer(num_speakers=0, status=lambda value: None):
    import sherpa_onnx
    cache = MODEL_DIR / "speakers"
    model = cache / "segmentation.onnx"
    if not model.is_file():
        archive = download(SEGMENTATION_URL, cache / "segmentation.tar.bz2", status)
        temporary = model.with_name(model.name + "." + uuid.uuid4().hex + ".part")
        try:
            with tarfile.open(archive, "r:bz2") as bundle:
                member = bundle.getmember("sherpa-onnx-pyannote-segmentation-3-0/model.onnx")
                # Extract only this regular file; never extract paths from an archive.
                if not member.isfile():
                    raise ValueError("Invalid speaker model archive")
                with bundle.extractfile(member) as source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target)
            temporary.replace(model)
        finally:
            temporary.unlink(missing_ok=True)
    embedding = download(EMBEDDING_URL, cache / "embedding.onnx", status)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(model)),
            num_threads=2,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=2),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_speakers or -1, threshold=0.5),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise ValueError("No se puede cargar el modelo de voces / Invalid speaker model")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


def label_segments(segments, turns):
    """Assign the greatest overlapping turn to each word; never invent a match."""
    turns = sorted(turns, key=lambda turn: turn[0])
    labels = {}
    for _, _, speaker in turns:
        if speaker not in labels:
            labels[speaker] = f"Speaker {len(labels) + 1}"
    result = []
    for segment in segments:
        pieces = segment.words or [(segment.start, segment.end, segment.text)]
        group = None
        for start, end, text in pieces:
            if not text.strip():
                continue
            scores = {}
            for turn_start, turn_end, speaker in turns:
                if turn_start >= end:
                    break
                overlap = max(0, min(end, turn_end) - max(start, turn_start))
                if overlap:
                    scores[speaker] = scores.get(speaker, 0) + overlap
            speaker = labels[max(scores, key=scores.get)] if scores else "Speaker ?"
            if group is not None and group.speaker == speaker:
                group.end = end
                group.text += text if text.startswith(" ") else " " + text
            else:
                group = Segment(start, end, text.strip(), speaker=speaker)
                result.append(group)
    return result


def diarize(diarizer, audio, segments, progress=lambda value: None):
    def callback(done, total):
        progress(done / max(total, 1) * 100)
        return 0
    turns = diarizer.process(audio, callback=callback).sort_by_start_time()
    if not turns:
        raise ValueError("No se detectaron voces / No speaker turns detected")
    return label_segments(segments, [(turn.start, turn.end, turn.speaker) for turn in turns])
