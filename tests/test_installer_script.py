import re
from pathlib import Path

SETUP_ISS = Path(__file__).resolve().parents[1] / "installer" / "setup.iss"


def _files_section_source_lines():
    text = SETUP_ISS.read_text(encoding="utf-8")
    match = re.search(r"^\[Files\]\n(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "[Files] section not found in setup.iss"
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip().startswith("Source:")
    ]


def test_setup_iss_files_section_has_no_duplicate_entries():
    """A duplicate Source/DestDir/DestName triple silently bundles the same file
    twice into the installer. This happened once undetected: ffmpeg.exe and
    ffprobe.exe were each embedded twice in the actual v1.0.0 build (~198MB of
    dead weight, only caught by comparing installer sizes across releases)."""
    seen = set()
    for line in _files_section_source_lines():
        source = re.search(r'Source:\s*"([^"]+)"', line).group(1)
        dest_dir_match = re.search(r'DestDir:\s*"([^"]+)"', line)
        dest_name_match = re.search(r'DestName:\s*"([^"]+)"', line)
        key = (
            source,
            dest_dir_match.group(1) if dest_dir_match else None,
            dest_name_match.group(1) if dest_name_match else source.rsplit("\\", 1)[-1],
        )
        assert key not in seen, f"Duplicate [Files] entry in setup.iss: {line}"
        seen.add(key)
