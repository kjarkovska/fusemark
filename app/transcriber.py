"""
transcriber.py — faster-whisper wrapper for ObsiNote

Transcribes an mp3/wav file to text using a local faster-whisper model.
Glossary terms are injected as an initial_prompt so Whisper spells them
correctly (canonical forms + aliases).

Model is downloaded on first use (~3 GB for large-v3) to the HuggingFace
cache directory and reused on every subsequent run.

CLI usage (Phase 3 test):
  python app/transcriber.py --file test.mp3
  python app/transcriber.py --file test.mp3 --model medium
"""

import argparse
import logging
import os
import time

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

from app import queue as q
from app.glossary import build_whisper_prompt
from app import config as cfg

MODEL_CACHE = {}   # module-level cache so the model loads only once per process


def _load_model(model_size):
    if model_size not in MODEL_CACHE:
        logger.info("Loading model '%s' (first run may download ~3 GB)...", model_size)
        MODEL_CACHE[model_size] = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",   # int8 is fastest on CPU, good quality
        )
        logger.info("Model loaded.")
    return MODEL_CACHE[model_size]


def transcribe(audio_path, model_size="large-v3", job_id=None):
    """
    Transcribe audio_path and return the full transcript as a string.

    If job_id is given, progress is written back to the job record in SQLite
    so the UI can show a live status.

    Raises FileNotFoundError if audio_path does not exist.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _load_model(model_size)
    initial_prompt = build_whisper_prompt()

    logger.info("Transcribing: %s", audio_path)
    start = time.time()

    segments, info = model.transcribe(
        audio_path,
        language="cs",            # Czech — force language, skip detection
        initial_prompt=initial_prompt,
        beam_size=5,
        vad_filter=True,          # skip silent gaps, speeds up transcription
        vad_parameters={"min_silence_duration_ms": 500},
    )

    transcript_parts = []
    duration = info.duration or 1  # avoid division by zero for very short clips

    for segment in segments:
        transcript_parts.append(segment.text.strip())

        if job_id:
            progress_pct = min(int((segment.end / duration) * 100), 99)
            elapsed = time.time() - start
            # Rough remaining time estimate based on real-time factor so far
            if segment.end > 0:
                rtf = elapsed / segment.end          # seconds of processing per second of audio
                remaining_audio = duration - segment.end
                eta_seconds = int(rtf * remaining_audio)
            else:
                eta_seconds = 0
            q.update_job(
                job_id,
                extra_context=f"transcribing:{progress_pct}%:eta:{eta_seconds}s",
            )

    elapsed_total = time.time() - start
    transcript = "\n".join(transcript_parts)

    logger.info(
        "Done in %.1fs (%.0fs audio, language=%s, prob=%.2f)",
        elapsed_total, info.duration, info.language, info.language_probability,
    )

    if job_id:
        q.update_job(job_id, transcript=transcript)

    return transcript


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ObsiNote transcriber — Phase 3 CLI test"
    )
    parser.add_argument(
        "--file",
        required=True,
        metavar="PATH",
        help="Path to the audio file to transcribe (mp3 or wav)",
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="SIZE",
        help="Whisper model size: large-v3 (default), medium, small",
    )
    args = parser.parse_args()

    config = cfg.load()
    model_size = args.model or config.get("whisper_model", "large-v3")

    transcript = transcribe(args.file, model_size=model_size)

    print("\n--- TRANSCRIPT ---")  # intentional stdout output for CLI use
    print(transcript)
    print("------------------\n")


if __name__ == "__main__":
    main()
