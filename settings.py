"""Validated, atomic per-user preferences; no recordings or transcript text."""

import json
import os
import tempfile
from pathlib import Path
from paths import USER_DATA

SETTINGS_PATH = USER_DATA / "settings.json"
LANGUAGES = {
    "Español": "es",
    "English": "en",
    "Automático / Auto": None,
    "Français": "fr",
    "Deutsch": "de",
    "Italiano": "it",
    "Português": "pt",
}
# Clustering threshold: higher merges similar voices, lower splits them.
SENSITIVITY = {
    "Menos voces / Fewer": 0.6,
    "Normal": 0.5,
    "Más voces / More": 0.4,
}
DEFAULTS = {
    "input_dir": "input_audio",
    "output_dir": "output_text",
    "language": "Español",
    "model": "small",
    "timestamps": False,
    "speakers": False,
    "speaker_count": "0",
    "speaker_sensitivity": "Normal",
    "word_output": True,
    "md_output": True,
    "srt_output": False,
}


def load_settings(path: Path | None = None) -> dict:
    result = DEFAULTS.copy()
    try:
        data = json.loads((path or SETTINGS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(data, dict):
        return result
    for key, default in DEFAULTS.items():
        value = data.get(key, default)
        if type(value) is not type(default):
            continue
        if key == "language" and value not in LANGUAGES:
            continue
        if key == "model" and value not in {"tiny", "base", "small", "medium", "large-v3"}:
            continue
        if key == "speaker_sensitivity" and value not in SENSITIVITY:
            continue
        if key == "speaker_count" and value not in {str(i) for i in range(21)}:
            continue
        if key in {"input_dir", "output_dir"} and (not value.strip() or "\0" in value):
            continue
        result[key] = value
    return result


def save_settings(values: dict, path: Path | None = None) -> None:
    path = path or SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({key: values[key] for key in DEFAULTS}, handle, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
