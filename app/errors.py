class PipelineError(Exception):
    """Base error for recoverable pipeline failures."""


class ConfigurationError(PipelineError):
    """Raised when required runtime configuration is missing."""


class ValidationError(PipelineError):
    """Raised when user input cannot be validated."""


class ProviderAuthError(PipelineError):
    """Raised when a provider rejects credentials."""


class ProviderRateLimitError(PipelineError):
    """Raised when a provider rate limit is hit."""


class ProviderTimeoutError(PipelineError):
    """Raised when a provider request times out."""


class ProviderConnectionError(PipelineError):
    """Raised when a provider cannot be reached."""


class ProviderHTTPError(PipelineError):
    """Raised when a provider returns a non-retryable HTTP error."""


class EmailSendError(PipelineError):
    """Raised when an email provider cannot send a message."""
