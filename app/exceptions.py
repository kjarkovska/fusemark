class ModelNotReadyError(Exception):
    """Raised when the Whisper model has not been downloaded yet."""


class TranscriptionAPIError(Exception):
    """Raised on HTTP errors from cloud transcription providers."""


class LLMRateLimitError(Exception):
    """Raised when the LLM provider returns a rate-limit response."""


class LLMAuthError(Exception):
    """Raised when the LLM provider rejects the API key."""
