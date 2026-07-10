"""
app/transcription/local.py — faster-whisper local transcription provider

Transcribes an audio file using a local faster-whisper model stored in
whisper_model_dir (defaults to %LOCALAPPDATA%/FuseMark/models).

Raises ModelNotReadyError if the model has not been downloaded yet.
"""

import logging
import os
import time

from app import config as cfg
from app import queue as q
from app.exceptions import ModelNotReadyError

logger = logging.getLogger(__name__)

MODEL_CACHE: dict = {}


def _repo_id(model_name: str) -> str:
    from faster_whisper.utils import _MODELS
    return _MODELS.get(model_name, f"Systran/faster-whisper-{model_name}")


def _model_is_downloaded(model_dir: str, model_name: str) -> bool:
    """Check if all required model files are present locally.

    Uses faster-whisper's own download_model(local_files_only=True) so the
    check mirrors exactly what model loading requires — avoids false positives
    from HuggingFace cache skeleton directories created at download start.
    """
    try:
        from faster_whisper.utils import download_model
        download_model(model_name, cache_dir=model_dir, local_files_only=True)
        return True
    except Exception:
        return False


def _load_model(model_size: str, model_dir: str):
    key = (model_size, model_dir)
    if key not in MODEL_CACHE:
        if not _model_is_downloaded(model_dir, model_size):
            raise ModelNotReadyError(
                "Whisper model not downloaded — go to Settings to download it."
            )
        from faster_whisper import WhisperModel
        logger.info("Loading model '%s'...", model_size)
        MODEL_CACHE[key] = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=model_dir,
        )
        logger.info("Model loaded.")
    return MODEL_CACHE[key]


def transcribe_local(
    audio_path: str,
    language: str,
    job_id: str | None,
    glossary_prompt: str,
) -> str:
    """
    Transcribe audio_path with the local Whisper model.

    language: ISO code (e.g. "cs", "en") or "auto" for auto-detection.
    job_id:   if provided, progress is written to SQLite so the UI can poll it.
    glossary_prompt: initial_prompt string for Whisper spelling hints.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    config = cfg.load()
    model_size = config.get("whisper_model", "large-v3-turbo")
    model_dir = config.get("whisper_model_dir", "")

    model = _load_model(model_size, model_dir)

    lang_param = None if language == "auto" else language

    logger.info("Transcribing: %s (language=%s)", audio_path, lang_param or "auto")
    start = time.time()

    segments, info = model.transcribe(
        audio_path,
        language=lang_param,
        initial_prompt=glossary_prompt,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    transcript_parts = []
    duration = info.duration or 1  # avoid division by zero for very short clips

    for segment in segments:
        transcript_parts.append(segment.text.strip())

        if job_id:
            progress_pct = min(int((segment.end / duration) * 100), 99)
            elapsed = time.time() - start
            if segment.end > 0:
                rtf = elapsed / segment.end
                remaining_audio = duration - segment.end
                eta_seconds = int(rtf * remaining_audio)
            else:
                eta_seconds = 0
            q.update_job(
                job_id,
                progress=progress_pct,
                eta=eta_seconds,
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
