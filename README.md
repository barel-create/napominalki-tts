# Napominalki TTS Client

Plays the family's lesson-reminder announcements out loud, and shows the
living-room dashboard in its own window. Replaces the old `C:\tts` setup
(tts_client.py + tts_runner.bat + chime.mp3, kept in sync between PCs with
Syncthing) with one downloadable app: get the `.exe`, run it once to enter
your Apps Script URL and token, and it just runs — no Python, no Syncthing,
no separate files to keep straight, and (as of the Sep 2026 GUI rewrite) no
black console window either.

It polls the same Apps Script `doGet ?action=tts` endpoint the bot already
serves, so it's a drop-in replacement — the Apps Script / Telegram side
(Code.gs) doesn't change at all.

## Get it running on Windows

1. Go to this repo's **Releases** page and download the latest `NapominalkiTTS.exe`.
2. Put it in its own folder (anywhere — Desktop, Downloads, doesn't matter).
3. Double-click it. A window opens showing the dashboard; click the gear
   icon (top-right) to open Settings and fill in:
   - **Apps Script Web App URL** — Save
   - **TTS token** — Save
   (both from the Napominalki project's `config.txt`). The app polls for
   reminders in the background as soon as both are saved — no restart needed.
4. Leave the window open (or minimize it). It behaves exactly like the old
   client: polls every 5s, speaks whatever the bot queues, skips anything
   older than 5 minutes.

A `config.json` is saved next to the `.exe` after your first save — delete
it (or edit it directly) to reconfigure or move to a new PC.

### The window

- **Main screen**: the family's existing Telegram dashboard (the same page
  reachable from the bot's Menu button), embedded directly — it refreshes
  itself automatically (about once a minute, matching how often the bot's
  own data actually changes) so it stays current without you doing anything.
- **Gear icon** (top-right): opens/closes Settings — click it again or press
  Esc to close.
- **Settings panel**: Web App URL / TTS token fields (each with its own Save
  button), a voice dropdown with a speaker-icon button that says a test
  phrase in the selected voice, sun/moon theme buttons, a borderless-window
  toggle, and an autoupdate toggle. All UI text and icons scale with the
  window — resize it as small or large as you like.
- **Update button**: appears beneath the dashboard only when autoupdate is
  off and a newer version exists on GitHub. Updating (auto or manual) closes
  the window for a few seconds while it swaps in the new version and
  relaunches — same as most desktop apps' auto-update, not instant/invisible.

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
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions (`.github/workflows/build.yml`) builds `NapominalkiTTS.exe` on
a Windows runner — bundling ffmpeg, the default chime, and the GUI shell
(web/) into the single file — and attaches it to a GitHub Release
automatically. No PyInstaller or Windows machine needed on your end to
produce it. **If uploading via the web UI instead of `git push`**: turn on
"show hidden files" first (dotfolders like `.github` are invisible by
default in Explorer/Finder/Nautilus) and select everything inside the
`napominalki-tts` folder at once, or the workflow file gets silently skipped
and Actions never runs.

**Version bumps**: `src/tts_client/version.py`'s `APP_VERSION` is what the
update check compares against GitHub's latest release tag. Bump it, tag a
matching release (`vX.Y.Z`), and the running app / update button will offer
it on their next check.

## Repo layout

```
run.py                     entry point (also what PyInstaller packages) -- launches the GUI
src/tts_client/
  config.py                settings load/save (config.json), GUI-safe (no blocking prompts)
  queue_client.py          polls the Apps Script TTS queue
  synth.py                 edge-tts synthesis + ffmpeg volume boost
  player.py                chime + voice playback (PowerShell MediaPlayer)
  autostart.py             installs/removes the Windows "run at login" entry
  version.py                APP_VERSION + GitHub repo info, for the updater
  updater.py                checks GitHub Releases, downloads + swaps in updates
  gui.py                    pywebview window setup, background poll thread
  gui_api.py                the JS <-> Python bridge (window.pywebview.api.*)
  main.py                  poll loop logic (poll_once/speak_item), reused by gui.py;
                            its own console entry point is no longer what ships
web/
  index.html               window layout: dashboard iframe, gear button, settings panel
  style.css                theme (light/dark) + fully responsive (clamp()-based) sizing
  app.js                   wires the UI to gui_api.py's bridge methods
assets/chime.wav            default chime (a user's own chime.mp3 overrides it)
build.spec                  PyInstaller build config (console=False, bundles web/)
.github/workflows/build.yml builds + releases the .exe on a version tag
```

## What changed vs. the old C:\tts setup

- **No more Syncthing / two-machine sync.** The app is the distribution
  mechanism now — a new PC downloads the current release instead of
  syncing a live-edited folder.
- **No more separate `tts_runner.bat`.** The poll loop itself never exits on
  a normal error (it logs and retries with backoff); Windows autostart is
  installed by the app on first run instead of a manually-placed shortcut.
- **Real window, not a console.** Settings, theme, the dashboard — all in
  one resizable window instead of a terminal + a separate browser tab.
- **Self-updating.** Checks GitHub for a newer release; either applies it
  automatically or offers a button, your choice (Settings → autoupdate).
- **Same TTS behavior otherwise**: same voice options (`ru-RU-DmitryNeural`
  locked default), same 5s poll / 300s stale-item cutoff, same edge-tts →
  ffmpeg volume boost → chime → voice pipeline, same shared-secret token.

The old PC + Syncthing setup is left running untouched — this is meant to be
tested side by side before anything gets decommissioned.
