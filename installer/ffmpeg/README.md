# Bundled ffmpeg

Place **`ffmpeg.exe`** and **`ffprobe.exe`** in this folder before building the installer.
They are bundled by `setup.iss` next to `ObsiNote.exe`, where `ffmpeg_exe()`
(`app/utils.py`, `sys.frozen` branch) finds them.

These binaries are **not committed to git** (see `.gitignore`) — they are large and
have their own licence.

## Where to get them

Download a static Windows build, e.g. from <https://www.gyan.dev/ffmpeg/builds/>
(the "essentials" build is enough), and copy `ffmpeg.exe` and `ffprobe.exe` from its
`bin\` folder into this directory.

## Licensing note

ffmpeg is distributed under LGPL/GPL depending on the build. Since ObsiNote ships
under **GPL v3**, bundling a GPL ffmpeg build is compatible. Keep a copy of the
ffmpeg licence with your distribution.
