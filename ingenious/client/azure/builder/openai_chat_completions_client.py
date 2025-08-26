"""
Azure OpenAI Chat Completions client builder (AutoGen).

Why:
- Preserve lazy identity import behavior.
- Support API key and AAD token provider authentication paths.

Usage:
    builder = AzureOpenAIChatCompletionClientBuilder(model_config)
    client = builder.build()
"""

from typing import Union

from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from ingenious.client.azure.builder.base import AzureClientBuilder
from ingenious.common.enums import AuthenticationMethod
from ingenious.config.auth_config import AzureAuthConfig
from ingenious.config.models import ModelSettings
from ingenious.models.config import ModelConfig


class AzureOpenAIChatCompletionClientBuilder(AzureClientBuilder):
    """Builder for Azure OpenAI Chat Completion clients using AutoGen."""

    def __init__(self, model_config: Union[ModelConfig, ModelSettings]) -> None:
        """Initialize builder and capture the model configuration."""
        # Extract authentication parameters from config
        auth_config = self._create_auth_config_from_model_config(model_config)
        super().__init__(auth_config=auth_config)
        self.model_config = model_config

    def _create_auth_config_from_model_config(
        self, model_config: Union[ModelConfig, ModelSettings]
    ) -> AzureAuthConfig:
        """Create AzureAuthConfig from model configuration."""
        return AzureAuthConfig.from_config(model_config)

    def build(self) -> AzureOpenAIChatCompletionClient:
        """
        Build Azure OpenAI Chat Completion client based on model configuration.

        Returns:
            AzureOpenAIChatCompletionClient: Configured AutoGen Azure OpenAI client.
        """
        # Get credential based on authentication method
        if self.auth_config.authentication_method == AuthenticationMethod.TOKEN:
            # Use API key authentication - need raw string value
            return AzureOpenAIChatCompletionClient(
                model=self.model_config.model or self.model_config.deployment,
                azure_deployment=self.model_config.deployment
                or self.model_config.model,
                api_version=self.model_config.api_version,
                azure_endpoint=self.model_config.base_url,
                api_key=self.api_key,
            )

        # Use Azure AD authentication (import at runtime to keep module light)
        from azure.identity import get_bearer_token_provider

        return AzureOpenAIChatCompletionClient(
            model=self.model_config.model or self.model_config.deployment,
            azure_deployment=self.model_config.deployment or self.model_config.model,
            api_version=self.model_config.api_version,
            azure_endpoint=self.model_config.base_url,
            azure_ad_token_provider=get_bearer_token_provider(
                self.token_credential, "https://cognitiveservices.azure.com/.default"
            ),
        )
