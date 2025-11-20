"""Verify exception handling for the AzureSearchRetriever.

This module contains tests to ensure that the AzureSearchRetriever component
correctly propagates exceptions that occur within its dependencies, namely the
Azure Cognitive Search client and the OpenAI embeddings client. The goal is to
confirm that failures in these external services are not silently swallowed but
are instead surfaced to the caller, allowing for proper error handling upstream.

Tests cover both lexical and vector search paths and simulate various non-transient
API errors, network issues, and authentication failures.
"""

from __future__ import annotations

import asyncio
from typing import Type
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import or define Azure exceptions
try:
    from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
except ImportError:
    # Define dummy exceptions if azure-core is not installed
    class ResourceNotFoundError(Exception):
        """Dummy exception for ResourceNotFoundError."""

        pass

    class HttpResponseError(Exception):
        """Dummy exception for HttpResponseError."""

        pass


# Mocking OpenAI exceptions
try:
    from openai import APIConnectionError, AuthenticationError, BadRequestError
except ImportError:
    # Define dummy exception classes if openai library is not installed
    class AuthenticationError(Exception):
        """Dummy exception for AuthenticationError."""

        def __init__(self, message: str, *args: object, **kwargs: object) -> None:
            """Initialize the dummy exception."""
            super().__init__(message)

    class APIConnectionError(Exception):
        """Dummy exception for APIConnectionError."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Initialize the dummy exception."""
            super().__init__("API Connection Error")

    class BadRequestError(Exception):
        """Dummy exception for BadRequestError."""

        def __init__(self, message: str, *args: object, **kwargs: object) -> None:
            """Initialize the dummy exception."""
            super().__init__(message)


from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever
from ingenious.services.azure_search.config import SearchConfig


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_to_raise, expected_exception",
    [
        (ResourceNotFoundError("Index not found (404)"), ResourceNotFoundError),
        (HttpResponseError("Bad Request - Invalid syntax (400)"), HttpResponseError),
        (HttpResponseError("Service Unavailable (503)"), HttpResponseError),
        (ConnectionError("Network issue"), ConnectionError),
    ],
)
async def test_retrieval_handles_azure_search_api_errors(
    config: SearchConfig,
    exception_to_raise: Exception,
    expected_exception: Type[Exception],
) -> None:
    """Test that Azure Search client exceptions are propagated correctly.

    This test verifies that when the underlying Azure Cognitive Search client
    raises an exception (e.g., for a missing index, bad request, or network issue),
    the AzureSearchRetriever allows the exception to propagate. This ensures that
    callers are notified of failures during both lexical and vector search operations.
    """
    # Setup: Mock clients
    mock_search_client = MagicMock()
    # Configure the search client to raise the specific exception
    mock_search_client.search = AsyncMock(side_effect=exception_to_raise)
    mock_embedding_client = MagicMock()

    retriever = AzureSearchRetriever(
        config, search_client=mock_search_client, embedding_client=mock_embedding_client
    )

    # Test Lexical Path
    with pytest.raises(expected_exception) as excinfo_lex:
        await retriever.search_lexical("test query")
    assert str(exception_to_raise) in str(excinfo_lex.value)

    # Test Vector Path
    # Ensure the embedding step succeeds so the error occurs during the search step
    mock_embedding_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
    )

    with pytest.raises(expected_exception) as excinfo_vec:
        await retriever.search_vector("test query")
    assert str(exception_to_raise) in str(excinfo_vec.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_to_raise, expected_exception",
    [
        (
            AuthenticationError(
                "Invalid API Key (401)", response=MagicMock(status_code=401), body={}
            ),
            AuthenticationError,
        ),
        (asyncio.TimeoutError("Embedding request timed out"), asyncio.TimeoutError),
        (APIConnectionError(request=MagicMock()), APIConnectionError),
        # Simulating a token limit exceeded error (400 Bad Request)
        (
            BadRequestError("Token limit exceeded", response=MagicMock(status_code=400), body={}),
            BadRequestError,
        ),
    ],
)
async def test_retrieval_handles_openai_embedding_errors(
    config: SearchConfig,
    exception_to_raise: Exception,
    expected_exception: Type[Exception],
) -> None:
    """Test that OpenAI embedding client exceptions are propagated correctly.

    This test ensures that exceptions raised by the OpenAI client during the
    embedding generation step of a vector search are properly propagated. This
    confirms that failures like authentication errors, timeouts, or token limits
    are surfaced to the caller instead of being suppressed.
    """
    # Setup: Mock clients
    mock_search_client = MagicMock()  # Should not be called if embedding fails
    mock_embedding_client = MagicMock()
    # Configure the embedding client's create method to raise the exception
    mock_embedding_client.embeddings.create = AsyncMock(side_effect=exception_to_raise)

    retriever = AzureSearchRetriever(
        config, search_client=mock_search_client, embedding_client=mock_embedding_client
    )

    # Execute Vector Path
    with pytest.raises(expected_exception) as excinfo:
        await retriever.search_vector("test query that causes error")

    # Assert the correct exception propagated and the search client was not called
    # For APIConnectionError, we can't check the message since it doesn't accept one
    if expected_exception != APIConnectionError:
        assert str(exception_to_raise) in str(excinfo.value)
    mock_search_client.search.assert_not_called()
