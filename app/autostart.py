"""
autostart.py — Windows auto-start management via the registry

Adds/removes a Run key so ObsiNote launches with Windows.
Uses HKEY_CURRENT_USER so no admin rights are required.

A .vbs launcher is written to the project root so wscript.exe can start
the app silently (no console flash) with the correct working directory.
"""

import logging
import os
import sys
import winreg

logger = logging.getLogger(__name__)

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ObsiNote"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VBS_PATH = os.path.join(PROJECT_ROOT, "start_obsinote.vbs")


def _is_frozen() -> bool:
    """True when running from a PyInstaller-packaged build (an installed .exe)."""
    return getattr(sys, "frozen", False)


def _pythonw():
    """Return path to pythonw.exe (no console window) in the same venv."""
    scripts = os.path.dirname(sys.executable)
    return os.path.join(scripts, "pythonw.exe")


def _write_vbs():
    """Write a silent VBScript launcher that sets the working directory."""
    pythonw = _pythonw()
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\n'
        f'sh.CurrentDirectory = "{PROJECT_ROOT}"\n'
        f'sh.Run Chr(34) & "{pythonw}" & Chr(34) & " -m app.main", 0, False\n'
    )
    with open(VBS_PATH, "w", encoding="utf-8") as f:
        f.write(vbs)


def _get_launch_cmd():
    """Return the registry Run command.

    Packaged build: launch the installed ObsiNote.exe directly (sys.executable
    is the app itself). Dev: wscript runs the .vbs launcher silently.
    """
    if _is_frozen():
        return f'"{sys.executable}"'
    wscript = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe")
    return f'"{wscript}" "{VBS_PATH}"'


def is_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def enable():
    if not _is_frozen():
        _write_vbs()  # dev only — packaged builds launch the .exe directly
    cmd = _get_launch_cmd()
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)
    logger.info("Enabled: %s", cmd)


def disable():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        logger.info("Disabled")
    except FileNotFoundError:
        pass
