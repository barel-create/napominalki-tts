"""
"Start with Windows" -- the app registers ITSELF to launch at user login.

Mechanism: a per-user value under
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
This is the standard way desktop apps self-register. Reasons it was chosen
over the alternatives (researched Oct 2026):
  * No admin rights needed (HKCU is the current user's own hive).
  * Launches in the user's normal interactive desktop session -- required,
    because the window uses WebView2, which does NOT work under a Windows
    Service / Session 0 (Microsoft: unsupported), so NSSM/service is out.
  * No console/cmd flash at login (the old Startup-folder .bat approach
    briefly opened a cmd window and needed a separate file to maintain).
  * Shows up in Task Manager -> Startup apps, where the user can disable it.
    That choice is stored by Windows separately (StartupApproved\\Run), so
    re-writing the Run value on every launch below does NOT override a user
    who switched it off.

Known limits (Microsoft docs, "Run and RunOnce Registry Keys"):
  * Fires only after a user LOGS IN -- if the PC reboots to a login screen
    and nobody signs in, nothing starts (auto-login must be set up for a
    fully hands-off PC).
  * Windows gives no guarantee how promptly Run entries start; it may delay
    them a few seconds after login on purpose.
  * The command line is limited to 260 characters.
  * This is launch-at-login only. It does NOT restart the app if it crashes
    mid-session.
"""

import os
import sys

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "NapominalkiTTS"

# Older (1.0.x console build) autostart wrote this .bat into the Startup
# folder. If it's still lying around next to the new registry entry, the app
# would launch twice at login, so install() removes it.
LEGACY_BAT_NAME = "NapominalkiTTS.bat"

MAX_COMMAND_LEN = 259  # Windows limit for Run command lines is 260 chars


def _target_exe():
    if getattr(sys, "frozen", False):
        return sys.executable
    return None  # running from source: nothing sensible to register


def _legacy_bat_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", LEGACY_BAT_NAME
    )


def _remove_legacy_bat():
    path = _legacy_bat_path()
    if path and os.path.exists(path):
        try:
            os.remove(path)
            print(f"[autostart] removed old Startup-folder entry: {path}")
        except OSError as e:
            print(f"[autostart] could not remove old Startup-folder entry {path}: {e}")


def _approved_state(winreg):
    """
    What Task Manager's "Startup apps" switch says about our entry.
    Returns "enabled", "disabled" or "unknown". Windows doesn't document this
    value's format; the widely observed convention is that the first byte is
    even (02/06) when enabled and odd (03/07) when the user disabled it. Only
    used to write one diagnostic line to log.txt -- never to change behavior.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY_PATH, 0, winreg.KEY_READ) as key:
            data, _type = winreg.QueryValueEx(key, VALUE_NAME)
        if data:
            return "disabled" if (data[0] & 1) else "enabled"
    except OSError:
        pass
    return "unknown"


def install():
    """
    Registers (or refreshes) the Run entry so it points at the exe that is
    running right now. Safe to call on every launch: if the exe was moved or
    renamed, the next launch repoints the entry. Returns True on success.
    Never raises.
    """
    if sys.platform != "win32":
        print("[autostart] not Windows; skipping")
        return False

    exe = _target_exe()
    if not exe:
        print("[autostart] running from source (not a packaged .exe); skipping")
        return False

    command = f'"{exe}"'  # quoted: install paths often contain spaces
    if len(command) > MAX_COMMAND_LEN:
        print(f"[autostart] exe path too long for a Run entry ({len(command)} chars): {exe}")
        return False

    try:
        import winreg
        existing = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                existing, _type = winreg.QueryValueEx(key, VALUE_NAME)
        except OSError:
            pass

        if existing == command:
            result = "already registered"
        else:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
            result = "registered" if existing is None else "updated (exe path changed)"

        _remove_legacy_bat()
        print(f"[autostart] {result}: {command} | Windows startup switch: {_approved_state(winreg)}")
        return True
    except Exception as e:
        print(f"[autostart] could not register for startup: {e}")
        return False


def uninstall():
    """Removes the Run entry (and the legacy .bat). Not used by the GUI today."""
    removed = False
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
            print("[autostart] removed Run entry")
            removed = True
        except OSError:
            pass
    path = _legacy_bat_path()
    if path and os.path.exists(path):
        try:
            os.remove(path)
            removed = True
        except OSError:
            pass
    return removed
