"""Test Azure Search service configuration builder helpers.

This module contains unit tests for the helper functions within the
`ingenious.services.azure_search.builders` module. Specifically, it focuses on
validating the `_validate_endpoint` function, which is critical for ensuring that
Azure Search service endpoints are correctly formatted and sanitized before use.
These tests cover both valid and invalid URL formats to guarantee robust error
handling and configuration.
"""

import pytest

from ingenious.services.azure_search.builders import ConfigError, _validate_endpoint


@pytest.mark.parametrize(
    "endpoint, expected_output",
    [
        ("https://valid.search.windows.net", "https://valid.search.windows.net"),
        ("http://localhost:8080/api", "http://localhost:8080/api"),
        (
            " https://spaced-url.com/path ",
            "https://spaced-url.com/path",
        ),  # Trimming verification
    ],
)
def test_validate_endpoint_valid_formats(endpoint: str, expected_output: str) -> None:
    """Verify that valid endpoint URL formats are accepted and normalized.

    This test ensures that the validator correctly processes various acceptable
    URL patterns, including standard Azure endpoints and local dev endpoints. It
    also confirms that leading/trailing whitespace is properly stripped.
    """
    assert _validate_endpoint(endpoint, "TestService") == expected_output


@pytest.mark.parametrize(
    "endpoint, error_message_substring",
    [
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
        ("ftp://invalid.scheme.com", "must use http or https scheme"),
        ("sftp://invalid.scheme.com", "must use http or https scheme"),
        ("just-the-hostname.com", "must be a valid URL with scheme and host"),
        ("https://", "must be a valid URL with scheme and host"),  # Missing host/netloc
        ("://missing.scheme/path", "must be a valid URL with scheme and host"),
    ],
)
def test_validate_endpoint_invalid_formats(endpoint: str, error_message_substring: str) -> None:
    """Verify that invalid endpoint URL formats raise a `ConfigError`.

    This test ensures that malformed, empty, or schemeless URLs are rejected
    with a `ConfigError` that contains a helpful, specific message explaining
    why the provided endpoint is invalid.
    """
    with pytest.raises(ConfigError) as excinfo:
        _validate_endpoint(endpoint, "TestService")

    # Verify the error message contains the expected diagnostic substring
    assert error_message_substring in str(excinfo.value)
