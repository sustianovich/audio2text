# Audio a texto

Local multilingual transcription to **Word (.docx)**, **Markdown (.md)** and **SRT subtitles (.srt)**, with automatic language detection and optional speaker labels.

## Windows installer

Download the latest **Audio2Text-Setup-<version>.exe** from this repository's [Releases](https://github.com/sustianovich/audio2text/releases). Run it and open **Audio2Text** from the Start menu. Python, FFmpeg, and the app dependencies are bundled; no separate Python installation is needed.

The installer is for 64-bit Windows. It installs for your current user and includes an uninstaller and an optional desktop shortcut. The build is unsigned. Models download on first use, so an Internet connection is initially required.

Installed-app recordings and transcripts default to `%LOCALAPPDATA%\Audio2Text\workspace\input_audio` and `output_text`. The UI displays the short folder names. Click **Open output folder** to find your results, or choose any folder with **Browse**. Models are cached in `%LOCALAPPDATA%\Audio2Text\models`. Uninstalling preserves these user files.

## Run from source

Install Python 3.10+ with Tkinter, then double-click **start.bat**. The launcher creates a virtual environment and installs dependencies.

Alternatively, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

For source runs, the workspace is the project folder and models are cached in **.models**. Relative folder paths are always resolved against the workspace, regardless of where you launch the app.

## Use

1. Put recordings in **input_audio**, or choose an input folder.
2. Click **Refresh** after typing a folder or adding files. Use Ctrl/Shift to select multiple recordings.
3. Choose an output folder (default: **output_text**).
4. Choose **Español** (default), **English**, French, German, Italian, Portuguese, or **Automático / Auto**, and a model. **small** balances quality and speed; tiny/base are faster, medium/large-v3 need more time and memory.
5. Check any combination of **Word (.docx)**, **Markdown (.md)** and **Subtitles (.srt)**. At least one is required. SRT always includes millisecond timestamps, independently of the document timestamps checkbox.
6. Optionally enable timestamps and **Speaker labels**. Set the speaker count to **0** for automatic detection, or enter a known count from 1 to 20.
7. Click **Transcribe**. **Cancel** stops the remaining work, including model loading and speaker analysis. Closing during a job offers to cancel and close.

Preferences (folders, language, model, output formats and speaker options) are saved when starting a job or closing the app, in `%LOCALAPPDATA%\Audio2Text\settings.json`. Invalid settings fall back to defaults. Automatic detection runs separately for each recording, and documents show its detected language.

Completed documents are kept when cancelling; no partial transcript is published for unfinished inference. If cancellation occurs while a completed recording is being exported, that export finishes safely first. You can start another job after cancellation.

Outputs include the source extension, e.g. recording.m4a.md and recording.m4a.docx. Repeated and simultaneous runs reserve a shared basename for the selected formats and add a number rather than overwriting existing files. Each file is published atomically on filesystems supporting hard links; other supported filesystems use exclusive creation. The group of formats is not a filesystem transaction, but export errors roll back files created by that export. Only the chosen folder is scanned, without subfolders.

Supported extensions: M4V, M4A, MP4, MP3, WAV, FLAC, OGG, AAC, WEBM, MOV, WMA. Video must contain a decodable audio track.

## Speaker labels

Local [sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/python.html) diarization uses a pyannote segmentation model and a CAMPPlus speaker embedding model distributed in the upstream releases. First use downloads approximately 37 MB of speaker models, separately from the transcription model. No account, API key, or access token is needed. Speaker downloads display byte/percentage progress, retry up to three times and verify pinned SHA-256 hashes before publication. Cached models are verified too; corrupted files are replaced only after a verified download. Whisper model loading remains indeterminate. The CAMPPlus embedding is unchanged; no unmeasured Spanish accuracy improvement is claimed.

Labels such as **Speaker 1** and **Speaker 2** are assigned in order of first appearance and restart for each recording. Word timestamps align the text with speaker turns, splitting paragraphs when the speaker changes. Unmatched words use **Speaker ?**, meaning no speaker turn overlapped those words. The system distinguishes voices; it does not identify people's real names.

Automatic speaker counts and labels can be wrong, especially with short speech, similar voices, noise, or overlapping speakers. Overlapping voices are assigned to the best matching turn per word rather than producing simultaneous transcripts. A known speaker count can improve grouping. Review important transcripts.

## Processing and privacy

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CPU and [python-docx](https://python-docx.readthedocs.io/en/latest/) for Word export. Audio and text are processed locally, without a transcription service. Downloads contact GitHub/Hugging Face for model files, not to upload recordings. Cached models are reused.

Language selects the language spoken in the recording; it does not translate. Large recordings can take substantial time and memory on CPU. Progress is shown for the current processing phase. Worker status and results travel through a bounded multiprocessing Queue; the parent owns document publication. Silence/no speech produces an error; failures in individual recordings are reported while other files continue.

The entire input_audio and output_text folders, models, virtual environment, build artifacts, and common credential/key files are excluded from Git. The installer is built from application code and package assets only. Never put credentials directly into source code.

## Build the installer

On Windows with Python and [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed:

```powershell
.\build_windows.ps1
```

This uses PyInstaller to produce **dist/Audio2Text/Audio2Text.exe**, then builds **release/Audio2Text-Setup-<version>.exe** (version from `pyproject.toml`). Models are downloaded at runtime and are not included in the installer. Dependency license metadata and the Python license are included in the bundle.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --self-test source-smoke.json
```

The packaged executable accepts the same `--self-test <report.json>` option. It checks bundled inference imports, voice activity detection, hidden UI startup, both speaker-labeled exports, and cancellation of a spawned worker. An optional `--integration-job <job.json>` runs a real-audio job for release verification; it can download models.

## Development

`pyproject.toml` is the single dependency/version source. The requirements files
remain compatible wrappers for the Windows launcher and existing build commands.

```powershell
.\.venv\Scripts\python.exe -m pip install ".[dev]"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GitHub Actions runs these checks on Windows with Python 3.10 and 3.13.
Tests use fake inference workers and temporary preferences; they need no model
downloads. They cover simultaneous exports, rollback, subtitle timing, language
detection, corrupt downloads, speaker overlaps and cancellation.

Speaker asset hashes were pinned from the existing release downloads and can be
reproduced with `Get-FileHash .models\speakers\* -Algorithm SHA256`.
Updating a model requires reviewing the new asset and updating its pinned hash.
