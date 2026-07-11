class ModelNotReadyError(Exception):
    """Raised when the Whisper model has not been downloaded yet."""


class TranscriptionAPIError(Exception):
    """Raised on HTTP errors from cloud transcription providers."""


class LLMRateLimitError(Exception):
    """Raised when the LLM provider returns a rate-limit response."""


class LLMAuthError(Exception):
    """Raised when the LLM provider rejects the API key."""


class LLMTransientError(Exception):
    """Raised on a connection failure or 5xx/overloaded response from the LLM provider — safe to retry."""


class LLMTruncatedError(Exception):
    """Raised when the LLM response was cut off at the max_tokens limit."""
