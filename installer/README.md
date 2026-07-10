# Building the FuseMark installer (Phase P11)

This folder packages FuseMark into a signed Windows installer.

- `build.spec` — PyInstaller spec (produces `dist\FuseMark\FuseMark.exe`, onedir).
- `setup.iss` — Inno Setup script (wraps `dist\` + ffmpeg into `FuseMarkSetup.exe`).
- `ffmpeg\` — drop `ffmpeg.exe` / `ffprobe.exe` here before building (see `ffmpeg\README.md`).

## One-time setup

1. Install [Inno Setup 6.3+](https://jrsoftware.org/isdl.php).
2. In the project venv: `pip install pyinstaller`.
3. Put `ffmpeg.exe` and `ffprobe.exe` in `installer\ffmpeg\`.

## Build steps

```powershell
# from the project root, venv active
pyinstaller installer\build.spec

# local smoke test BEFORE making the installer — copy ffmpeg next to the exe:
copy installer\ffmpeg\ffmpeg.exe  dist\FuseMark\
copy installer\ffmpeg\ffprobe.exe dist\FuseMark\
dist\FuseMark\FuseMark.exe
#   -> verify the window opens AND that recording works (PortAudio/ctranslate2 DLLs
#      are the usual packaging failure points — they fail silently if missing).

# sign the app exe (see "Code signing" below), then build the installer:
iscc installer\setup.iss
#   -> produces installer\Output\FuseMarkSetup.exe

# sanity-check the size against the previous release before uploading — a large
# unexplained jump usually means something got bundled twice (this happened once:
# ffmpeg.exe + ffprobe.exe were each embedded twice in the v1.0.0 build, ~198MB of
# dead weight, only caught by comparing sizes across releases). The [Files] section
# itself is guarded by tests/test_installer_script.py, but that only catches
# duplicate lines in setup.iss — not other packaging mistakes — so still compare:
(Get-Item installer\Output\FuseMarkSetup.exe).Length / 1MB
gh release view <previous-tag> --json assets --jq '.assets[0].size' # bytes; divide by 1MB to compare

# sign the installer too, then test on a clean Windows VM with NO Python installed.
```

## Cutting a release (version bump)

The runtime version lives in **`app/version.py`** (`VERSION`). At release time keep
two values in sync, then tag:

1. `app/version.py` → `VERSION = "x.y.z"`
2. `installer/setup.iss` → `#define MyAppVersion "x.y.z"`
3. `git tag vx.y.z && git push --tags`

## Code signing (required before public distribution)

Windows SmartScreen blocks unknown-publisher executables. Sign **both** the app exe
and the installer:

```powershell
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\FuseMark\FuseMark.exe
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a installer\Output\FuseMarkSetup.exe
```

Certificate options (evaluate cost vs. UX):

| Option | Cost (approx) | SmartScreen |
|---|---|---|
| **Azure Trusted Signing** | ~$10/month | Cheapest; check individual/EU eligibility first |
| OV certificate | €100–250/yr | Removes hard block; warns until download reputation builds |
| EV certificate | €300–500/yr | No warning on first download |

## Test checklist (clean Windows 10 + 11, no Python)

- [ ] Installer runs (UAC prompt for Program Files is expected)
- [ ] App launches from Start Menu and Desktop shortcut; tray icon appears; window opens
- [ ] First-run wizard appears
- [ ] Recording works (system audio + mic) — no PortAudio/DLL errors in the log
- [ ] Transcription works (model downloads to `whisper_model_dir`)
- [ ] Note generation works (all providers)
- [ ] Auto-start toggle works (and points at `FuseMark.exe`, not pythonw)
- [ ] Uninstaller removes app files; user data in `%APPDATA%\FuseMark` is preserved
- [ ] Uninstaller removes the `HKCU\...\Run\FuseMark` autostart value
- [ ] SmartScreen does not block the signed installer
