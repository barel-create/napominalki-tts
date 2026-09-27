# Napominalki TTS Client

Plays the family's lesson-reminder announcements out loud. Replaces the old
`C:\tts` setup (tts_client.py + tts_runner.bat + chime.mp3, kept in sync
between PCs with Syncthing) with one downloadable program: get the `.exe`,
run it once to enter your Apps Script URL and token, and it just runs —
no Python, no Syncthing, no separate files to keep straight.

It polls the same Apps Script `doGet ?action=tts` endpoint the bot already
serves, so it's a drop-in replacement — the Apps Script / Telegram side
(Code.gs) doesn't change at all.

## Get it running on a PC

1. Go to this repo's **Releases** page and download the latest `NapominalkiTTS.exe`.
2. Put it in its own folder (anywhere — Desktop, Downloads, doesn't matter).
3. Double-click it. First run asks for two values from the Napominalki
   project's `config.txt`:
   - **Apps Script Web App URL** (`WEB_APP_URL`)
   - **TTS token** (`TTS_TOKEN`)
   It also asks whether to start automatically at login — say yes for the
   always-on speaker PC.
4. That's it. Leave the window open (or minimized). It polls every 5s and
   speaks whatever the bot queues, same as before.

A `config.json` is saved next to the `.exe` after setup — delete it (or edit
it directly) to reconfigure or move to a new PC.

### Optional: your own chime

Drop a `chime.mp3` or `chime.wav` in the same folder as the `.exe` and it'll
play that instead of the built-in default chime.

## Publishing this repo (for Barel)

This was built in a sandbox with no push access to `barel-create` on GitHub,
so the last step is on you:

```bash
cd napominalki-tts
git init
git add .
git commit -m "Initial TTS client"
git remote add origin https://github.com/barel-create/napominalki-tts.git
git push -u origin main
```

(Create the empty repo on github.com first if it doesn't exist yet — same as
`napominalki-dashboard`.)

Then tag a release to trigger the build:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions (`.github/workflows/build.yml`) builds `NapominalkiTTS.exe` on
a Windows runner — bundling ffmpeg and the default chime into the single
file — and attaches it to a GitHub Release automatically. No PyInstaller or
Windows machine needed on your end to produce it.

## Repo layout

```
run.py                     entry point (also what PyInstaller packages)
src/tts_client/
  config.py                first-run setup wizard, config.json load/save
  queue_client.py          polls the Apps Script TTS queue
  synth.py                 edge-tts synthesis + ffmpeg volume boost
  player.py                chime + voice playback (PowerShell MediaPlayer)
  autostart.py             installs/removes the Windows "run at login" entry
  main.py                  the poll loop that ties it together
assets/chime.wav            default chime (a user's own chime.mp3 overrides it)
build.spec                  PyInstaller build config
.github/workflows/build.yml builds + releases the .exe on a version tag
```

## What changed vs. the old C:\tts setup

- **No more Syncthing / two-machine sync.** The app is the distribution
  mechanism now — a new PC downloads the current release instead of
  syncing a live-edited folder.
- **No more separate `tts_runner.bat`.** The poll loop itself never exits on
  a normal error (it logs and retries with backoff); Windows autostart is
  installed by the app on first run instead of a manually-placed shortcut.
- **Same behavior otherwise**: same voice (`ru-RU-DmitryNeural`), same
  5s poll / 300s stale-item cutoff, same edge-tts → ffmpeg volume boost →
  chime → voice pipeline, same shared-secret token in the query string.
- **Trade-off worth knowing:** editing the client is no longer instant.
  Before, saving the `.py` file on the Mint PC pushed to the Windows PC in
  seconds (Syncthing + mtime-watch). Now, a code change means: edit here,
  push, tag a release, redownload the `.exe` on the target PC. Slower, but
  the whole point was fewer moving parts on the PC that just needs to work.

The old PC + Syncthing setup is left running untouched — this is meant to be
tested side by side before anything gets decommissioned.
