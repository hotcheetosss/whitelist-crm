"""Domain errors. Each class maps to one HTTP status code (see main.py handlers).

`code` is machine-readable (English), `message` is for a human (Russian).
"""

from typing import Any


class DomainError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    """The request is valid, but conflicts with the current state of data."""

    status_code = 409


class ValidationFailed(DomainError):
    """The request breaks a business rule about its own content (e.g. working hours)."""

    status_code = 422
