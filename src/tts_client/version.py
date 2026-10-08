"""
Single source of truth for the app's own version number.

Bump this + tag a matching GitHub release (e.g. bump to "1.1.0" here, then
`git tag v1.1.0 && git push origin v1.1.0`) whenever a change should be
offered to users via the update button / autoupdate. updater.py compares
this against the latest GitHub Release's tag_name.
"""

APP_VERSION = "1.1.3"  # vs 1.1.2: always-on log.txt (UTF-8, set up before pywebview), live status line, every poll/speak step logged, timeouts

GITHUB_OWNER = "barel-create"
GITHUB_REPO = "napominalki-tts"
