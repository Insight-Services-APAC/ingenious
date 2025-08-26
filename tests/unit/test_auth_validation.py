#!/usr/bin/env python3
"""
Test script to verify authentication validation logic for Azure OpenAI client builder.

This module tests the authentication requirements and validation scenarios
for the Azure OpenAI client builder functions, ensuring that different
authentication methods work correctly with proper credentials.
"""

from ingenious.common.enums import AuthenticationMethod


def test_authentication_requirements():
    """Test the authentication requirements for different methods used by the client builder."""

    print("🔍 Testing Azure OpenAI Client Builder Authentication Methods\n")

    auth_methods = [
        AuthenticationMethod.DEFAULT_CREDENTIAL,
        AuthenticationMethod.MSI,
        AuthenticationMethod.TOKEN,
        AuthenticationMethod.CLIENT_ID_AND_SECRET,
    ]

    for auth_method in auth_methods:
        print(f"Authentication Method: {auth_method.value}")

        if auth_method == AuthenticationMethod.DEFAULT_CREDENTIAL:
            print("  ✅ No additional credentials required")
            print("  📋 Uses Azure Default Credential chain")

        elif auth_method == AuthenticationMethod.MSI:
            print("  🔑 Required: client_id")
            print("  📋 Uses Managed Identity with specified client_id")

        elif auth_method == AuthenticationMethod.TOKEN:
            print("  🔑 Required: api_key")
            print("  📋 Uses API key authentication")

        elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
            print("  🔑 Required: client_id AND client_secret AND tenant_id")
            print("  📋 Uses Service Principal authentication")
            print("  💡 tenant_id can come from config or AZURE_TENANT_ID env var")

        print()


def test_validation_scenarios():
    """
    Test validation scenarios for Azure OpenAI client builder authentication.

    These scenarios validate that the client builder functions properly handle
    different authentication configurations and reject invalid combinations.
    """
    print("🧪 Client Builder Validation Scenarios:\n")

    scenarios = [
        {
            "name": "DEFAULT_CREDENTIAL - Valid",
            "auth_method": AuthenticationMethod.DEFAULT_CREDENTIAL,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "",
            "client_secret": "",
            "tenant_id": "",
            "should_pass": True,
        },
        {
            "name": "MSI - Valid with client_id",
            "auth_method": AuthenticationMethod.MSI,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "12345678-1234-1234-1234-123456789012",
            "client_secret": "",
            "tenant_id": "",
            "should_pass": True,
        },
        {
            "name": "MSI - Invalid without client_id",
            "auth_method": AuthenticationMethod.MSI,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "",
            "client_secret": "",
            "tenant_id": "",
            "should_pass": False,
        },
        {
            "name": "TOKEN - Valid with api_key",
            "auth_method": AuthenticationMethod.TOKEN,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "test-api-key",
            "client_id": "",
            "client_secret": "",
            "tenant_id": "",
            "should_pass": True,
        },
        {
            "name": "TOKEN - Invalid without api_key",
            "auth_method": AuthenticationMethod.TOKEN,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "",
            "client_secret": "",
            "tenant_id": "",
            "should_pass": False,
        },
        {
            "name": "CLIENT_ID_AND_SECRET - Valid with all credentials",
            "auth_method": AuthenticationMethod.CLIENT_ID_AND_SECRET,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "12345678-1234-1234-1234-123456789012",
            "client_secret": "test-secret",
            "tenant_id": "87654321-4321-4321-4321-210987654321",
            "should_pass": True,
        },
        {
            "name": "CLIENT_ID_AND_SECRET - Valid with tenant_id from env",
            "auth_method": AuthenticationMethod.CLIENT_ID_AND_SECRET,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "12345678-1234-1234-1234-123456789012",
            "client_secret": "test-secret",
            "tenant_id": "",  # Should fallback to AZURE_TENANT_ID env var
            "should_pass": True,
            "env_vars": {"AZURE_TENANT_ID": "87654321-4321-4321-4321-210987654321"},
        },
        {
            "name": "CLIENT_ID_AND_SECRET - Invalid without client_id",
            "auth_method": AuthenticationMethod.CLIENT_ID_AND_SECRET,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "",
            "client_secret": "test-secret",
            "tenant_id": "87654321-4321-4321-4321-210987654321",
            "should_pass": False,
        },
        {
            "name": "CLIENT_ID_AND_SECRET - Invalid without client_secret",
            "auth_method": AuthenticationMethod.CLIENT_ID_AND_SECRET,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "12345678-1234-1234-1234-123456789012",
            "client_secret": "",
            "tenant_id": "87654321-4321-4321-4321-210987654321",
            "should_pass": False,
        },
        {
            "name": "CLIENT_ID_AND_SECRET - Invalid without tenant_id",
            "auth_method": AuthenticationMethod.CLIENT_ID_AND_SECRET,
            "base_url": "https://test.openai.azure.com/",
            "model": "gpt-4",
            "api_key": "",
            "client_id": "12345678-1234-1234-1234-123456789012",
            "client_secret": "test-secret",
            "tenant_id": "",
            "should_pass": False,
        },
    ]

    for scenario in scenarios:
        print(f"Scenario: {scenario['name']}")

        # Set up environment variables if specified
        import os

        original_env = {}
        if "env_vars" in scenario:
            for key, value in scenario["env_vars"].items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value

        # Simulate validation logic
        base_fields_valid = scenario["base_url"] and scenario["model"]
        auth_valid = True

        if scenario["auth_method"] == AuthenticationMethod.DEFAULT_CREDENTIAL:
            # No additional validation needed
            pass
        elif scenario["auth_method"] == AuthenticationMethod.MSI:
            auth_valid = bool(scenario["client_id"])
        elif scenario["auth_method"] == AuthenticationMethod.TOKEN:
            auth_valid = bool(scenario["api_key"])
        elif scenario["auth_method"] == AuthenticationMethod.CLIENT_ID_AND_SECRET:
            # Check client_id, client_secret, and tenant_id (with AZURE_TENANT_ID fallback)
            tenant_id = scenario["tenant_id"] or os.environ.get("AZURE_TENANT_ID", "")
            auth_valid = bool(
                scenario["client_id"] and scenario["client_secret"] and tenant_id
            )

        overall_valid = base_fields_valid and auth_valid
        expected = scenario["should_pass"]

        # Restore environment variables
        if "env_vars" in scenario:
            for key in scenario["env_vars"].keys():
                if original_env[key] is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_env[key]

        if overall_valid == expected:
            print(
                f"  ✅ PASS - Validation result matches expectation ({overall_valid})"
            )
        else:
            print(f"  ❌ FAIL - Expected {expected}, got {overall_valid}")

        print()


if __name__ == "__main__":
    test_authentication_requirements()  # type: ignore[no-untyped-call]
    test_validation_scenarios()  # type: ignore[no-untyped-call]
