"""
Azure OpenAI (sync) client builder.

Why:
- Keep import-time light and preserve lazy identity imports.
- Support both API key and AAD token provider authentication paths.

Usage:
    builder = AzureOpenAIClientBuilder(model_config)
    client = builder.build()
"""

from typing import Union

from openai import AzureOpenAI

from ingenious.client.azure.builder.base import AzureClientBuilder
from ingenious.common.enums import AuthenticationMethod
from ingenious.config.auth_config import AzureAuthConfig
from ingenious.config.models import ModelSettings
from ingenious.models.config import ModelConfig


class AzureOpenAIClientBuilder(AzureClientBuilder):
    """Builder for Azure OpenAI clients with multiple authentication methods."""

    def __init__(self, model_config: Union[ModelConfig, ModelSettings]) -> None:
        """Extract authentication parameters and store the model config."""
        # Extract authentication parameters from config
        auth_config = self._create_auth_config_from_model_config(model_config)
        super().__init__(auth_config=auth_config)
        self.model_config = model_config

    def _create_auth_config_from_model_config(
        self, model_config: Union[ModelConfig, ModelSettings]
    ) -> AzureAuthConfig:
        """Create AzureAuthConfig from model configuration."""
        return AzureAuthConfig.from_config(model_config)

    def build(self) -> AzureOpenAI:
        """
        Build Azure OpenAI client based on model configuration.

        Returns:
            AzureOpenAI: Configured Azure OpenAI client.
        """
        # Get credential based on authentication method
        if self.auth_config.authentication_method == AuthenticationMethod.TOKEN:
            # Use API key authentication - need raw string value
            return AzureOpenAI(
                azure_endpoint=self.model_config.base_url,
                api_version=self.model_config.api_version,
                api_key=self.api_key,
            )

        # Use Azure AD authentication (import at runtime to keep module light)
        from azure.identity import get_bearer_token_provider

        return AzureOpenAI(
            azure_endpoint=self.model_config.base_url,
            api_version=self.model_config.api_version,
            azure_ad_token_provider=get_bearer_token_provider(
                self.token_credential, "https://cognitiveservices.azure.com/.default"
            ),
        )
