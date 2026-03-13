"""
autostart.py — Windows auto-start management via the registry

Adds/removes a Run key so Granola-CZ launches with Windows.
Uses HKEY_CURRENT_USER so no admin rights are required.
"""

import os
import sys
import winreg

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Granola-CZ"


def _get_launch_cmd():
    """Return the command that should be registered for auto-start."""
    python = sys.executable
    main = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "main.py")
    return f'"{python}" -m app.main'


def is_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def enable():
    cmd = _get_launch_cmd()
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)
    print(f"[autostart] Enabled: {cmd}")


def disable():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("[autostart] Disabled")
    except FileNotFoundError:
        pass
