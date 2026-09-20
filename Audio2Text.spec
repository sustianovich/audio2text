# Build contains package assets only, never user recordings, transcripts, or models.
from pathlib import Path
import sys
from importlib.metadata import distributions
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

datas, binaries, hiddenimports = [], [], []
for package in ("faster_whisper", "ctranslate2", "sherpa_onnx"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
datas += collect_data_files("docx")
# Preserve dependency licenses and metadata in distributable builds.
for distribution in distributions():
    datas += copy_metadata(distribution.metadata["Name"])
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/python"))
a = Analysis(["app.py"], pathex=[], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=["torch", "tensorflow", "pytest", "IPython"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Audio2Text",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Audio2Text")
