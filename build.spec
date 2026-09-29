# PyInstaller spec. Built by .github/workflows/build.yml on windows-latest,
# which first downloads a static ffmpeg.exe into the repo root (git-ignored,
# CI-only) before running `pyinstaller build.spec`. Bundling ffmpeg + the
# default chime + the web/ GUI shell into the single .exe is what makes
# "download and run" work with nothing else to install on the target PC.
#
# console=False (Sep 2026 GUI rewrite): no more black terminal window --
# the app is a pywebview window now (see gui.py). Anything printed via
# print()/traceback still happens, it just has nowhere visible to go in a
# normal double-click launch; that's an accepted trade-off of "no console".

import os

block_cipher = None

binaries = []
if os.path.exists("ffmpeg.exe"):
    binaries.append(("ffmpeg.exe", "."))

datas = []
if os.path.exists("assets/chime.wav"):
    datas.append(("assets/chime.wav", "."))

# Bundle the whole web/ GUI shell (index.html, style.css, app.js), preserving
# its relative layout so gui.py's _web_dir()/_index_path() find it the same
# way whether running from source or frozen.
if os.path.isdir("web"):
    for root, _dirs, files in os.walk("web"):
        for name in files:
            src = os.path.join(root, name)
            dest_dir = root  # already "web" or "web/<subdir>" -- kept as-is
            datas.append((src, dest_dir))

a = Analysis(
    ["run.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "edge_tts",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr_loader",
    ],
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
    console=False,
    onefile=True,
    clean=True,
    upx=False,
)
