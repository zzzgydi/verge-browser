class VergeError(Exception):
    """Base error for Verge Browser SDK and CLI."""


class VergeConfigError(VergeError):
    """Raised when local CLI or SDK configuration is incomplete."""


class VergeAuthError(VergeError):
    """Raised when the API rejects authentication."""


class VergeNotFoundError(VergeError):
    """Raised when a sandbox cannot be found."""


class VergeConflictError(VergeError):
    """Raised when the requested change conflicts with server state."""


class VergeValidationError(VergeError):
    """Raised when input fails server-side validation."""


class VergeServerError(VergeError):
    """Raised when the server returns an unexpected failure."""
