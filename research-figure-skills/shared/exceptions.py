class ValidationError(ValueError):
    """Raised when an input violates a scientific contract."""


class SourceIntegrityError(FileNotFoundError):
    """Raised when declared evidence cannot be read or verified."""
