# Changelog

## Unreleased

- Normalize audio level (DC offset, speech-level gain, peak limit) before VAD,
  transcription and speaker identification; warn about very quiet or clipped audio.
- Group segments into paragraphs in Word/Markdown by pause, speaker and sentence
  end, and cap decoding-loop repetitions. SRT keeps the original short cues.
- Speaker labels: absorb isolated mislabelled words, assign words in small gaps to
  the nearest turn, and add a voice-split sensitivity setting.

## 1.2.0

- Persist validated preferences and add automatic detection and more language choices.
- Export SRT subtitles with millisecond timestamps and optional speaker labels.
- Replace JSON mailbox polling with a bounded multiprocessing Queue.
- Verify speaker model downloads and cached assets with pinned SHA-256 hashes;
  retry failed downloads and report download progress.
- Narrow speaker overlap searches using binary searches without losing long turns.
- Reserve output basenames across processes and publish without overwriting files.
- Centralize dependencies/version in pyproject.toml; add Ruff and Windows CI.
- Expand regression coverage for cancellation, collisions, rollback, corrupt
  preferences/downloads, automatic detection and subtitles.

## 1.1.0

- Local speaker labels, cancellable child-process inference and Windows installer.
