"""
recorder.py — Audio capture for FuseMark

Captures two separate streams simultaneously:
  - System audio via WASAPI loopback (pyaudiowpatch)
  - Microphone input (pyaudiowpatch)

Frames are streamed straight to two partial WAV files on disk as they arrive
(recordings/.partial/<session_id>.{system,mic}.wav) instead of being buffered
in memory for the whole meeting. stop() closes the WAV handles (patching
their headers); save() hands the finished files to ffmpeg to mix + resample
into a single mp3, then deletes them. If the process dies mid-recording, the
partial WAVs survive with an unpatched header — salvage_partial() repairs and
recovers them on the next startup (see recording_service.salvage_interrupted_recordings).

CLI usage:
  python app/recorder.py --list-devices
  python app/recorder.py --test
  python app/recorder.py --test --duration 30
  python app/recorder.py --test --output-device 4 --input-device 1
"""

import argparse
import logging
import os
import subprocess
import threading
import time
import uuid
import wave

import numpy as np
import pyaudiowpatch as pyaudio

from app.utils import ffmpeg_exe

logger = logging.getLogger(__name__)

CHUNK = 1024
FORMAT = pyaudio.paInt16   # int16 — 2 bytes per sample
OUTPUT_BITRATE = "64k"

# Level-meter tuning. RMS is expressed as a 0.0-1.0 fraction of int16 full
# scale — typical speech sits around 0.02-0.15, so these thresholds/decay
# are picked for "does this look like a live mic", not loudness accuracy.
SILENCE_THRESHOLD = 0.005   # RMS below this counts as silence, ~-46 dBFS
SILENCE_SECONDS = 10.0      # how long without signal before levels() flags silent
_LEVEL_DECAY = 0.7          # per-callback decay applied to the held peak


class Recorder:
    def __init__(self, output_device=None, input_device=None, session_id=None):
        """
        output_device: index of the output device whose audio to loopback-capture.
                       None = use the system default output device.
        input_device:  index of the microphone.
                       None = use the system default input device.
        session_id:    identifies this recording's partial WAV files on disk —
                       normally the job id, so a crash mid-recording can be
                       matched back to its job at startup. None = random.
        """
        self._output_device = output_device
        self._input_device = input_device
        self._session_id = session_id or uuid.uuid4().hex

        self._lock = threading.Lock()

        self._pa = None
        self._system_stream = None
        self._mic_stream = None

        # Set during start() — needed by save()
        self._system_rate = None
        self._system_channels = None
        self._mic_rate = None
        self._mic_channels = None

        # Partial WAV handles + paths + running byte counts — replaces the old
        # in-memory frame lists so an N-hour meeting no longer costs N hours of RAM.
        self._system_wav = None
        self._mic_wav = None
        self._system_wav_path = None
        self._mic_wav_path = None
        self._system_bytes = 0
        self._mic_bytes = 0

        # Level meter state — decayed-peak RMS per stream, plus a monotonic
        # timestamp of the last time each stream was above SILENCE_THRESHOLD,
        # so levels() can report "no signal for N seconds" (see start()).
        self._system_level = 0.0
        self._mic_level = 0.0
        self._system_last_loud_at = time.monotonic()
        self._mic_last_loud_at = time.monotonic()

    # ------------------------------------------------------------------
    # Device helpers
    # ------------------------------------------------------------------

    def _find_loopback(self):
        """Return the pyaudiowpatch device-info dict for the loopback device
        that corresponds to the configured output device."""
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)

        if self._output_device is not None:
            target = self._pa.get_device_info_by_index(self._output_device)
        else:
            target = self._pa.get_device_info_by_index(
                wasapi["defaultOutputDevice"]
            )

        # If the device is already a loopback, return it directly
        if target.get("isLoopbackDevice", False):
            return target

        # Find the corresponding loopback device by name match
        for loopback in self._pa.get_loopback_device_info_generator():
            if target["name"] in loopback["name"]:
                return loopback

        raise RuntimeError(
            f"No WASAPI loopback device found for output: '{target['name']}'. "
            "Make sure WASAPI loopback is enabled on your system."
        )

    def _find_mic(self):
        """Return the device-info dict for the configured mic."""
        if self._input_device is not None:
            return self._pa.get_device_info_by_index(self._input_device)
        return self._pa.get_default_input_device_info()

    # ------------------------------------------------------------------
    # Stream callbacks — called from a separate thread by pyaudio
    # ------------------------------------------------------------------

    def _system_callback(self, in_data, frame_count, time_info, status):
        level = _rms_int16(in_data)
        with self._lock:
            self._system_level = max(level, self._system_level * _LEVEL_DECAY)
            if level >= SILENCE_THRESHOLD:
                self._system_last_loud_at = time.monotonic()
            wav = self._system_wav
            if wav is not None:
                try:
                    wav.writeframesraw(in_data)
                    self._system_bytes += len(in_data)
                except Exception:
                    # Must never raise out of a PortAudio callback — that
                    # silently kills the stream with no user-visible error.
                    logger.exception("Dropped a system-audio chunk")
        return (None, pyaudio.paContinue)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        level = _rms_int16(in_data)
        with self._lock:
            self._mic_level = max(level, self._mic_level * _LEVEL_DECAY)
            if level >= SILENCE_THRESHOLD:
                self._mic_last_loud_at = time.monotonic()
            wav = self._mic_wav
            if wav is not None:
                try:
                    wav.writeframesraw(in_data)
                    self._mic_bytes += len(in_data)
                except Exception:
                    logger.exception("Dropped a mic-audio chunk")
        return (None, pyaudio.paContinue)

    def levels(self) -> dict:
        """Current signal levels — polled by GET /level while recording."""
        with self._lock:
            now = time.monotonic()
            return {
                "system": self._system_level,
                "mic": self._mic_level,
                "system_bytes": self._system_bytes,
                "mic_bytes": self._mic_bytes,
                "system_silent": (now - self._system_last_loud_at) >= SILENCE_SECONDS,
                "mic_silent": (now - self._mic_last_loud_at) >= SILENCE_SECONDS,
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        self._pa = pyaudio.PyAudio()
        self._system_level = 0.0
        self._mic_level = 0.0
        self._system_last_loud_at = time.monotonic()
        self._mic_last_loud_at = time.monotonic()

        try:
            loopback = self._find_loopback()
            self._system_rate = int(loopback["defaultSampleRate"])
            self._system_channels = min(int(loopback["maxInputChannels"]), 2)

            mic = self._find_mic()
            self._mic_rate = int(mic["defaultSampleRate"])
            self._mic_channels = 1

            # Open the partial WAVs before the streams, so a callback can
            # never fire before self._system_wav / self._mic_wav exist.
            self._system_wav_path, self._mic_wav_path = partial_paths(self._session_id)
            self._system_bytes = 0
            self._mic_bytes = 0
            self._system_wav = _open_partial_wav(
                self._system_wav_path, self._system_channels, self._system_rate
            )
            self._mic_wav = _open_partial_wav(
                self._mic_wav_path, self._mic_channels, self._mic_rate
            )

            self._system_stream = self._pa.open(
                format=FORMAT,
                channels=self._system_channels,
                rate=self._system_rate,
                input=True,
                input_device_index=loopback["index"],
                frames_per_buffer=CHUNK,
                stream_callback=self._system_callback,
            )

            self._mic_stream = self._pa.open(
                format=FORMAT,
                channels=self._mic_channels,
                rate=self._mic_rate,
                input=True,
                input_device_index=mic["index"],
                frames_per_buffer=CHUNK,
                stream_callback=self._mic_callback,
            )

            self._system_stream.start_stream()
            self._mic_stream.start_stream()
        except Exception:
            # Clean up whatever opened before the failure (e.g. a BT mic that
            # disconnected between loopback and mic stream open) instead of
            # leaking the stream + PyAudio instance + partial WAV files.
            self.stop()
            self._discard_partials()
            raise

    def stop(self):
        if self._system_stream:
            self._system_stream.stop_stream()
            self._system_stream.close()
            self._system_stream = None
        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None

        # stop_stream() above blocks until in-flight callbacks finish, so no
        # callback can be running by the time we close the WAV handles.
        with self._lock:
            for attr in ("_system_wav", "_mic_wav"):
                wav = getattr(self, attr)
                if wav is None:
                    continue
                setattr(self, attr, None)  # clear first: a stray callback then no-ops
                try:
                    wav.close()  # patches the RIFF/data chunk sizes
                except Exception:
                    logger.warning("Failed to close partial WAV (%s)", attr, exc_info=True)

    def _discard_partials(self):
        """Delete the partial WAV files and reset path/byte state. Idempotent."""
        for attr in ("_system_wav_path", "_mic_wav_path"):
            path = getattr(self, attr)
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("Failed to remove partial WAV: %s", path)
            setattr(self, attr, None)
        self._system_bytes = 0
        self._mic_bytes = 0

    def discard(self):
        """Close everything and drop the partial WAVs without producing an mp3.
        For failure paths where save() will never run. Idempotent — safe to
        call after stop() or after save() has already cleaned up."""
        self.stop()
        self._discard_partials()

    def save(self, path):
        """Mix both partial WAVs and write to path as .mp3. Returns path."""
        if self._system_wav is not None or self._mic_wav is not None:
            self.stop()

        with self._lock:
            system_path = self._system_wav_path
            mic_path = self._mic_wav_path
            total_bytes = self._system_bytes + self._mic_bytes

        if not total_bytes:
            self._discard_partials()
            raise RuntimeError("Nothing was recorded.")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        try:
            # ffmpeg mixes the two streams, resamples to 16 kHz mono, encodes mp3
            result = subprocess.run(
                [
                    ffmpeg_exe(), "-y",
                    "-i", system_path,
                    "-i", mic_path,
                    "-filter_complex", "amix=inputs=2:duration=longest",
                    "-ar", "16000",
                    "-ac", "1",
                    "-b:a", OUTPUT_BITRATE,
                    path,
                ],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")
        finally:
            self._discard_partials()

        logger.info("Saved: %s", path)
        return path


# ------------------------------------------------------------------
# Level-meter helper
# ------------------------------------------------------------------

def _rms_int16(data: bytes) -> float:
    """RMS of int16 PCM as a 0.0-1.0 fraction of full scale.

    numpy, not the stdlib audioop module — audioop was removed in Python
    3.13. This project's dev venv runs 3.13 while CI pins 3.12 (where
    audioop still exists), so an audioop-based implementation would pass
    CI and then crash on the next `python -m app.main` outside it.
    """
    if not data:
        return 0.0
    usable = data[: (len(data) // 2) * 2]  # drop a trailing odd byte, if any
    if not usable:
        return 0.0
    samples = np.frombuffer(usable, dtype=np.int16)
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)) / 32768.0)


# ------------------------------------------------------------------
# Partial-file helpers — module-level so startup salvage can use them
# without constructing a Recorder.
# ------------------------------------------------------------------

def partial_dir() -> str:
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, "recordings", ".partial")


def partial_paths(session_id: str) -> tuple:
    d = partial_dir()
    return (
        os.path.join(d, f"{session_id}.system.wav"),
        os.path.join(d, f"{session_id}.mic.wav"),
    )


def _open_partial_wav(path, channels, rate):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wf = wave.open(path, "wb")
    wf.setnchannels(channels)
    wf.setsampwidth(2)  # FORMAT = paInt16 = 2 bytes
    wf.setframerate(rate)
    return wf


def list_partial_sessions() -> list:
    """Return session ids (job ids) with at least a system partial WAV on disk."""
    d = partial_dir()
    if not os.path.isdir(d):
        return []
    suffix = ".system.wav"
    return [name[: -len(suffix)] for name in os.listdir(d) if name.endswith(suffix)]


def rewrite_wav_header(path: str) -> bool:
    """Repair a WAV left with a stale header by a crash mid-write.

    wave.Wave_write only patches the RIFF/data chunk sizes on close(); a
    process killed mid-recording leaves a header that undersells (or zeroes)
    how much PCM data actually follows it. Scans the chunk list for 'data',
    trusts the file's actual size for its length, and rewrites just the two
    size fields in place. Returns False if the file isn't a parseable
    RIFF/WAVE container or has no usable data chunk.
    """
    try:
        file_size = os.path.getsize(path)
        with open(path, "r+b") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return False

            data_header_offset = None
            data_size_on_disk = None
            pos = 12
            while pos + 8 <= file_size:
                f.seek(pos)
                chunk_id = f.read(4)
                size_bytes = f.read(4)
                if len(chunk_id) < 4 or len(size_bytes) < 4:
                    break
                declared_size = int.from_bytes(size_bytes, "little")
                if chunk_id == b"data":
                    data_header_offset = pos
                    data_size_on_disk = file_size - (pos + 8)
                    break
                advance = declared_size + (declared_size % 2)  # chunks are word-padded
                if advance <= 0:
                    break
                pos += 8 + advance

            if not data_header_offset or not data_size_on_disk or data_size_on_disk <= 0:
                return False

            f.seek(4)
            f.write((file_size - 8).to_bytes(4, "little"))
            f.seek(data_header_offset + 4)
            f.write(data_size_on_disk.to_bytes(4, "little"))
        return True
    except OSError:
        return False


def salvage_partial(session_id: str, out_path: str) -> str | None:
    """Repair and mix a crash-orphaned session's partial WAVs into out_path.

    Returns out_path on success, None if nothing usable was recoverable.
    Always deletes the partial WAVs afterward, whether salvage succeeded or not.
    """
    system_path, mic_path = partial_paths(session_id)
    system_ok = os.path.exists(system_path) and rewrite_wav_header(system_path)
    mic_ok = os.path.exists(mic_path) and rewrite_wav_header(mic_path)

    try:
        if system_ok and mic_ok:
            args = [
                ffmpeg_exe(), "-y",
                "-i", system_path, "-i", mic_path,
                "-filter_complex", "amix=inputs=2:duration=longest",
                "-ar", "16000", "-ac", "1", "-b:a", OUTPUT_BITRATE, out_path,
            ]
        elif system_ok or mic_ok:
            args = [
                ffmpeg_exe(), "-y",
                "-i", system_path if system_ok else mic_path,
                "-ar", "16000", "-ac", "1", "-b:a", OUTPUT_BITRATE, out_path,
            ]
        else:
            return None

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        result = subprocess.run(
            args, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            logger.warning("Salvage ffmpeg failed for session %s: %s", session_id, result.stderr)
            return None
        return out_path
    finally:
        for p in (system_path, mic_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    logger.warning("Failed to remove partial WAV after salvage: %s", p)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def list_devices():
    """Print all audio devices with their index, type, and loopback/default markers."""
    pa = pyaudio.PyAudio()
    try:
        print("\nAvailable audio devices:")
        print("-" * 70)
        default_in = pa.get_default_input_device_info()["index"]
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = wasapi["defaultOutputDevice"]
        except Exception:
            default_out = pa.get_default_output_device_info()["index"]

        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            kinds = []
            if d["maxInputChannels"] > 0:
                kinds.append("IN ")
            if d["maxOutputChannels"] > 0:
                kinds.append("OUT")
            markers = []
            if i == default_in:
                markers.append("default input")
            if i == default_out:
                markers.append("default output")
            if d.get("isLoopbackDevice", False):
                markers.append("LOOPBACK")
            marker_str = f"  ← {', '.join(markers)}" if markers else ""
            print(f"  [{i:2d}] {'|'.join(kinds):7s}  {d['name']}{marker_str}")
        print()
    finally:
        pa.terminate()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="FuseMark recorder — Phase 1 CLI test"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Record a test clip and save as test.mp3 in the project root",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Duration in seconds for --test mode (default: 10)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices and exit",
    )
    parser.add_argument(
        "--output-device",
        type=int,
        default=None,
        metavar="INDEX",
        help="Device index for system audio loopback (default: system default output)",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        metavar="INDEX",
        help="Device index for microphone (default: system default input)",
    )
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    if args.test:
        list_devices()
        recorder = Recorder(
            output_device=args.output_device,
            input_device=args.input_device,
        )
        print(f"Recording for {args.duration}s — play some audio and speak into the mic...")
        try:
            recorder.start()
            time.sleep(args.duration)
        except KeyboardInterrupt:
            print("\nStopped early.")
        finally:
            recorder.stop()

        out = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test.mp3")
        recorder.save(out)
        print("Done. Play test.mp3 and verify both system audio and mic are audible.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
