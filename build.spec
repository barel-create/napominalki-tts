# PyInstaller spec. Built by .github/workflows/build.yml on windows-latest,
# which first downloads a static ffmpeg.exe into the repo root (git-ignored,
# CI-only) before running `pyinstaller build.spec`. Bundling ffmpeg + the
# default chime into the single .exe is what makes "download and run" work
# with nothing else to install on the target PC.

import os

block_cipher = None

binaries = []
if os.path.exists("ffmpeg.exe"):
    binaries.append(("ffmpeg.exe", "."))

datas = []
if os.path.exists("assets/chime.wav"):
    datas.append(("assets/chime.wav", "."))

a = Analysis(
    ["run.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=["edge_tts"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NapominalkiTTS",
    console=True,
    onefile=True,
    clean=True,
    upx=False,
)
