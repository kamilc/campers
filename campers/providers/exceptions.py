"""Provider-agnostic exception classes for cloud provider operations.

These exceptions abstract away cloud-provider-specific details (e.g., AWS botocore)
and provide a unified interface for error handling across different providers.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all provider-related errors."""

    pass


class ProviderCredentialsError(ProviderError):
    """Raised when cloud provider credentials are missing or invalid.

    This abstracts cloud-provider-specific credential errors like
    botocore.exceptions.NoCredentialsError (AWS) to provide a unified
    error handling interface across different providers.
    """

    pass


class ProviderAPIError(ProviderError):
    """Raised when a cloud provider API call fails.

    This abstracts cloud-provider-specific API errors like
    botocore.exceptions.ClientError (AWS) to provide a unified
    error handling interface across different providers.
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        original_exception: Exception | None = None,
    ) -> None:
        """Initialize ProviderAPIError.

        Parameters
        ----------
        message : str
            Human-readable error message
        error_code : str | None
            Provider-specific error code (e.g., 'UnauthorizedOperation')
        original_exception : Exception | None
            Original provider-specific exception for debugging
        """
        super().__init__(message)
        self.error_code = error_code
        self.original_exception = original_exception


class ProviderConnectionError(ProviderError):
    """Raised when unable to connect to cloud provider API.

    This abstracts cloud-provider-specific connection errors like
    botocore.exceptions.EndpointConnectionError (AWS).
    """

    pass


__all__ = [
    "ProviderError",
    "ProviderCredentialsError",
    "ProviderAPIError",
    "ProviderConnectionError",
]
