"""Test edge cases for Azure Search configuration builder utilities.

This module contains tests for helper functions within the Azure Search builders,
focusing specifically on validation logic. It ensures that malformed inputs,
such as invalid endpoint URLs, are correctly identified and raise appropriate
exceptions, safeguarding the configuration process.
"""

from __future__ import annotations

import pytest

from ingenious.services.azure_search.builders import ConfigError, _validate_endpoint


@pytest.mark.parametrize(
    "invalid_url",
    [
        "example.com",  # Missing scheme
        "ftp://example.com",  # Invalid scheme
        "https://",  # Missing host
        "",  # Empty
        "  ",  # Whitespace
    ],
)
def test_builders_validate_endpoint_malformed_urls(invalid_url: str) -> None:
    """Verify _validate_endpoint rejects malformed URLs.

    This test ensures that URLs with missing schemes, invalid schemes, missing hosts,
    or that are empty/whitespace are correctly identified as invalid, triggering
    a ConfigError.
    """
    with pytest.raises(ConfigError):
        _validate_endpoint(invalid_url, "Test Endpoint")


def test_builders_validate_endpoint_valid_url() -> None:
    """Verify _validate_endpoint accepts and cleans a valid URL.

    This test confirms that a correctly formatted URL, even with leading/trailing
    whitespace, passes validation and is returned in a canonical, stripped form.
    """
    valid_url: str = "  https://valid.example.com/path  "
    expected: str = "https://valid.example.com/path"
    assert _validate_endpoint(valid_url, "Test Endpoint") == expected
