"""Separate installed application assets from writable user data."""

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
PROJECT = Path(__file__).resolve().parent
USER_DATA = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "Audio2Text"
)
ROOT = USER_DATA / "workspace" if FROZEN else PROJECT
MODEL_DIR = USER_DATA / "models" if FROZEN else PROJECT / ".models"
