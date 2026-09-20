# Audio a texto

Desktop app for local Spanish or English transcription into **Word (.docx)** and **Markdown (.md)**.

## Start on Windows

Install Python 3.10+ with Tkinter (included in the standard Windows installer) and double-click **start.bat**. The launcher creates a local virtual environment and installs dependencies. Internet is needed for setup and the first use of each model.

Alternatively, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

After setup, the last command launches directly without checking packages online.

## Use

1. Put recordings in **input_audio**, or choose an input folder in the UI.
2. Click **Refresh** after typing a folder or adding recordings. Select files (Ctrl/Shift for multiple).
3. Choose the output folder (default: **output_text**).
4. Choose **Español** (default) or **English**, and a model. Start with **small**; tiny/base are faster, medium/large-v3 need more time and memory.
5. Optionally enable timestamps, then click **Transcribe**.

Both output formats are always created. Outputs include the source extension, e.g. recording.m4a.md and recording.m4a.docx. Repeated runs add a number rather than overwriting transcripts. Files are scanned in the chosen folder only, not subfolders.

Supported extensions: M4V, M4A, MP4, MP3, WAV, FLAC, OGG, AAC, WEBM, MOV, WMA. Video must contain a decodable audio track. The recording is decoded directly; no intermediate audio file or separate FFmpeg installation is needed.

## Processing and privacy

Uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CPU and [python-docx](https://python-docx.readthedocs.io/en/latest/) for Word export. Models are downloaded to **.models** and reused. Audio is processed locally without an API key or transcription service. Large recordings can take substantial time on CPU; progress begins after model loading and audio decoding. The UI remains responsive while processing. Wait for the job to finish before closing.

Language selects the language spoken in the recording; it does not translate. Automatic transcripts can contain mistakes. Speaker identification is not included. Silence/no detected speech produces an error rather than empty documents. Failures are reported per file and other selected files continue.

The entire input_audio and output_text folders, downloaded models, virtual environment, and common credential/key files are excluded from Git. The app creates the input and output folders automatically on startup after cloning. Never place credentials directly in source code.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
