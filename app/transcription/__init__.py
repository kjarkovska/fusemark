from app import config as cfg
from app.glossary import build_whisper_prompt


def transcribe(audio_path: str, job_id: str | None = None) -> str:
    """Dispatch to the configured transcription provider. Returns full transcript string."""
    config = cfg.load()
    provider = config.get("transcription_provider", "whisper_local")

    if provider == "whisper_local":
        from app.transcription.local import transcribe_local
        language = config.get("language", "cs")
        glossary_prompt = build_whisper_prompt()
        return transcribe_local(audio_path, language, job_id, glossary_prompt)

    raise ValueError(
        f"Unknown transcription_provider: {provider} — "
        "cloud mode coming in v1.1"
    )
