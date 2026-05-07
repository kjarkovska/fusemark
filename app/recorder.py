"""
recorder.py — Audio capture for ObsiNote

Captures two separate streams simultaneously:
  - System audio via WASAPI loopback (pyaudiowpatch)
  - Microphone input (pyaudiowpatch)

Frames are collected in memory, then written as two temp WAV files at each
device's native sample rate. ffmpeg mixes + resamples both to a single mp3.

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
import sys
import tempfile
import threading
import time
import wave

import pyaudiowpatch as pyaudio

from app.utils import ffmpeg_exe

logger = logging.getLogger(__name__)

CHUNK = 1024
FORMAT = pyaudio.paInt16   # int16 — 2 bytes per sample
OUTPUT_BITRATE = "64k"


class Recorder:
    def __init__(self, output_device=None, input_device=None):
        """
        output_device: index of the output device whose audio to loopback-capture.
                       None = use the system default output device.
        input_device:  index of the microphone.
                       None = use the system default input device.
        """
        self._output_device = output_device
        self._input_device = input_device

        self._system_frames = []
        self._mic_frames = []
        self._lock = threading.Lock()

        self._pa = None
        self._system_stream = None
        self._mic_stream = None

        # Set during start() — needed by save()
        self._system_rate = None
        self._system_channels = None
        self._mic_rate = None
        self._mic_channels = None

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
        with self._lock:
            self._system_frames.append(in_data)
        return (None, pyaudio.paContinue)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        with self._lock:
            self._mic_frames.append(in_data)
        return (None, pyaudio.paContinue)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        self._system_frames = []
        self._mic_frames = []
        self._pa = pyaudio.PyAudio()

        loopback = self._find_loopback()
        self._system_rate = int(loopback["defaultSampleRate"])
        self._system_channels = min(int(loopback["maxInputChannels"]), 2)

        mic = self._find_mic()
        self._mic_rate = int(mic["defaultSampleRate"])
        self._mic_channels = 1

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

    def save(self, path):
        """Mix both streams and write to path as .mp3. Returns path."""
        with self._lock:
            system_frames = list(self._system_frames)
            mic_frames = list(self._mic_frames)

        if not system_frames and not mic_frames:
            raise RuntimeError("Nothing was recorded.")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        system_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        mic_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        system_tmp.close()
        mic_tmp.close()

        try:
            _write_wav(
                system_tmp.name,
                system_frames,
                self._system_channels,
                self._system_rate,
            )
            _write_wav(
                mic_tmp.name,
                mic_frames,
                self._mic_channels,
                self._mic_rate,
            )

            # ffmpeg mixes the two streams, resamples to 16 kHz mono, encodes mp3
            result = subprocess.run(
                [
                    ffmpeg_exe(), "-y",
                    "-i", system_tmp.name,
                    "-i", mic_tmp.name,
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
            os.unlink(system_tmp.name)
            os.unlink(mic_tmp.name)

        logger.info("Saved: %s", path)
        return path


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _write_wav(path, frames, channels, rate):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # FORMAT = paInt16 = 2 bytes
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))


def list_devices():
    """Print all audio devices with their index, type, and loopback/default markers."""
    pa = pyaudio.PyAudio()
    try:
        print("\nAvailable audio devices:")
        print("-" * 70)
        wasapi_idx = None
        try:
            wasapi_idx = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        except Exception:
            pass

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
        description="ObsiNote recorder — Phase 1 CLI test"
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
