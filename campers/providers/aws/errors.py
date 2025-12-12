"""AWS error handling and translation utilities."""

from contextlib import contextmanager

from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from campers.providers.exceptions import (
    ProviderAPIError,
    ProviderConnectionError,
    ProviderCredentialsError,
)

CREDENTIAL_ERROR_CODES = frozenset(
    {
        "ExpiredTokenException",
        "ExpiredToken",
        "RequestExpired",
        "InvalidClientTokenId",
        "InvalidToken",
        "TokenRefreshRequired",
        "UnrecognizedClientException",
    }
)


@contextmanager
def handle_aws_errors():
    """Context manager to translate AWS exceptions to ProviderError hierarchy.

    Yields
    ------
    None

    Raises
    ------
    ProviderCredentialsError
        When AWS credentials are not configured or invalid
    ProviderAPIError
        When AWS API call fails
    ProviderConnectionError
        When unable to connect to AWS API
    """
    try:
        yield
    except NoCredentialsError as e:
        raise ProviderCredentialsError("Cloud provider credentials not configured") from e
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        message = e.response.get("Error", {}).get("Message", str(e))

        if error_code in CREDENTIAL_ERROR_CODES or "expired" in message.lower():
            raise ProviderCredentialsError(
                f"AWS credentials expired or invalid: {message}. "
                "Refresh your credentials and try again."
            ) from e

        raise ProviderAPIError(message=message, error_code=error_code, original_exception=e) from e
    except EndpointConnectionError as e:
        raise ProviderConnectionError(f"Unable to connect to cloud provider API: {e}") from e
