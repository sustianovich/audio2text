"""Local speaker turns and word-level alignment using sherpa-onnx."""

from pathlib import Path
import hashlib
import time
from bisect import bisect_left, bisect_right
import shutil
import tarfile
import urllib.request
import uuid

from paths import MODEL_DIR
from transcription import Segment

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = (
    RELEASES + "/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
# Upstream release tag really is spelled "recongition"; do not correct it.
EMBEDDING_URL = (
    RELEASES + "/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"
)


# Pinned SHA-256 of the release assets and extracted segmentation model.
HASHES = {
    SEGMENTATION_URL: "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488",
    EMBEDDING_URL: "357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b",
}
SEGMENTATION_HASH = "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, destination, status, expected_hash=None):
    """Validate cached assets and publish only verified complete downloads."""
    expected_hash = expected_hash or HASHES[url]
    destination = Path(destination)
    if destination.is_file() and checksum(destination) == expected_hash:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".part")
    try:
        for attempt in range(3):
            try:
                with (
                    urllib.request.urlopen(url, timeout=60) as response,
                    temporary.open("wb") as output,
                ):
                    total = int(response.headers.get("Content-Length", 0))
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        received += len(chunk)
                        detail = f"{received / total:.0%}" if total else f"{received // 1024} KiB"
                        status(f"Descargando modelo de voces / Downloading speaker model: {detail}")
                if checksum(temporary) != expected_hash:
                    raise ValueError("Speaker model SHA-256 mismatch")
                temporary.replace(destination)
                return destination
            except (OSError, ValueError):
                if attempt == 2:
                    raise
                status(f"Reintentando descarga / Retrying download ({attempt + 2}/3)...")
                time.sleep(2**attempt)
    finally:
        temporary.unlink(missing_ok=True)


def load_diarizer(num_speakers=0, status=lambda value: None, threshold=0.5):
    import sherpa_onnx

    cache = MODEL_DIR / "speakers"
    model = cache / "segmentation.onnx"
    if not model.is_file() or checksum(model) != SEGMENTATION_HASH:
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
            if checksum(temporary) != SEGMENTATION_HASH:
                raise ValueError("Segmentation model SHA-256 mismatch")
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
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers or -1, threshold=threshold
        ),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise ValueError("No se puede cargar el modelo de voces / Invalid speaker model")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


NEAREST_TURN_GAP = 1.5  # A word this close to a turn still belongs to its speaker.
SHORT_RUN_SECONDS = 0.5  # A speaker run shorter than this, ...
SHORT_RUN_WORDS = 2  # ... with at most this many words, is suspect.
SANDWICH_GAP = 1.0  # A short run between the same speaker is absorbed if this close.
BOUNDARY_GAP = 0.3  # A short run touching a neighbour joins it if this close.


def _speaker_of(start, end, turns, starts, prefix_ends, prefix_turn):
    """Speaker with the largest overlap, else the nearest turn within a small gap.

    Turns are sorted by start. `prefix_ends[i]` is the latest end among turns[:i + 1] and
    `prefix_turn[i]` the index of the first turn reaching it, so both searches are
    logarithmic instead of scanning every turn.
    """
    scores = {}
    first = bisect_right(prefix_ends, start)  # Turns before this all end by `start`.
    last = bisect_left(starts, end)  # Turns from this on all start at or after `end`.
    for turn_start, turn_end, speaker in turns[first:last]:
        overlap = max(0, min(end, turn_end) - max(start, turn_start))
        if overlap:
            scores[speaker] = scores.get(speaker, 0) + overlap
    if scores:
        return max(scores, key=scores.get)
    # No overlap: only the latest-ending earlier turn, the turns touching the word and the
    # first later turn can be nearest. Checked in index order so ties match a full scan.
    candidates = [prefix_turn[first - 1]] if first else []
    candidates += range(first, last)
    if last < len(turns):
        candidates.append(last)
    nearest, distance = None, NEAREST_TURN_GAP
    for index in candidates:
        turn_start, turn_end, speaker = turns[index]
        gap = max(0, turn_start - end, start - turn_end)
        if gap < distance:
            nearest, distance = speaker, gap
    return nearest


def _smooth(entries):
    """Fix isolated words that alignment put on the wrong side of a speaker change.

    Entries are [segment_index, start, end, text, speaker]. Only short runs are
    touched, and only towards a neighbour that is close in time.
    """
    runs = []
    for entry in entries:
        if runs and runs[-1][0][4] == entry[4]:
            runs[-1].append(entry)
        else:
            runs.append([entry])
    decisions = []
    for index in range(1, len(runs) - 1):
        run, before, after = runs[index], runs[index - 1], runs[index + 1]
        speaker = run[0][4]
        if (
            speaker is None
            or len(run) > SHORT_RUN_WORDS
            or run[-1][2] - run[0][1] >= SHORT_RUN_SECONDS
        ):
            continue
        gap_before = run[0][1] - before[-1][2]
        gap_after = after[0][1] - run[-1][2]
        neighbour = None
        if before[0][4] == after[0][4] and max(gap_before, gap_after) < SANDWICH_GAP:
            neighbour = before[0][4]
        elif min(gap_before, gap_after) <= BOUNDARY_GAP:
            candidate = before if gap_before <= gap_after else after
            neighbour = candidate[0][4]
        if neighbour is not None:
            decisions.append((run, neighbour))
    for run, neighbour in decisions:
        for entry in run:
            entry[4] = neighbour


def label_segments(segments, turns):
    """Label each word with its speaker, then clean up isolated mislabelled words.

    Words with no nearby speaker turn are labelled "Speaker ?" rather than guessed.
    """
    turns = sorted(turns, key=lambda turn: turn[0])
    labels = {}
    for _, _, speaker in turns:
        if speaker not in labels:
            labels[speaker] = f"Speaker {len(labels) + 1}"
    starts = [turn[0] for turn in turns]
    prefix_ends, prefix_turn = [], []
    for index, (_, end, _) in enumerate(turns):
        if prefix_ends and prefix_ends[-1] >= end:
            prefix_ends.append(prefix_ends[-1])
            prefix_turn.append(prefix_turn[-1])
        else:
            prefix_ends.append(end)
            prefix_turn.append(index)
    entries = []
    for number, segment in enumerate(segments):
        pieces = segment.words or [(segment.start, segment.end, segment.text)]
        for start, end, text in pieces:
            if text.strip():
                speaker = _speaker_of(start, end, turns, starts, prefix_ends, prefix_turn)
                entries.append([number, start, end, text, speaker])
    _smooth(entries)
    result = []
    group = None
    for number, start, end, text, speaker in entries:
        speaker = labels[speaker] if speaker is not None else "Speaker ?"
        if group is not None and group[0] == number and group[1].speaker == speaker:
            group[1].end = end
            group[1].text += text if text.startswith(" ") else " " + text
        else:
            segment = Segment(start, end, text.strip(), speaker=speaker)
            group = (number, segment)
            result.append(segment)
    return result


def diarize(diarizer, audio, segments, progress=lambda value: None):
    def callback(done, total):
        progress(done / max(total, 1) * 100)
        return 0

    turns = diarizer.process(audio, callback=callback).sort_by_start_time()
    if not turns:
        raise ValueError("No se detectaron voces / No speaker turns detected")
    return label_segments(segments, [(turn.start, turn.end, turn.speaker) for turn in turns])
