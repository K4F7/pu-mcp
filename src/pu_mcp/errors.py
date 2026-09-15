from __future__ import annotations


class PuToolError(Exception):
    """Base exception for this package."""


class AuthError(PuToolError):
    """Authentication failed or session expired."""


class RiskControlError(PuToolError):
    """Captcha, risk control, abnormal login, or device verification required."""


class RateLimitError(PuToolError):
    """Request was rate limited."""


class BusinessError(PuToolError):
    """A non-retryable platform business error."""


class NetworkError(PuToolError):
    """A transient network error after bounded retries."""


class ParseError(PuToolError):
    """The response shape did not match the expected contract."""
