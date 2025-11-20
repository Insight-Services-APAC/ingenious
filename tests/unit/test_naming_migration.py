"""Tests for PEP 8 naming migration and backward compatibility."""

import sys
import warnings
from unittest.mock import MagicMock

import pytest

# Mock openai module before importing service.py
sys.modules["openai"] = MagicMock()
sys.modules["openai.types"] = MagicMock()
sys.modules["openai.types.chat"] = MagicMock()


class TestMultiAgentChatServiceNaming:
    """Test backward compatibility of multi_agent_chat_service naming."""

    def test_class_alias_exists(self):
        """Test that the old class name is still available as an alias."""
        from ingenious.services.chat_services.multi_agent.service import (
            MultiAgentChatService,
            multi_agent_chat_service,
        )

        # Verify the alias points to the same class
        assert multi_agent_chat_service is MultiAgentChatService


class TestFileStorageNaming:
    """Test that FileStorage uses lowercase parameter names."""

    def test_category_parameter_accepted(self):
        """Test that category parameter (lowercase) is accepted."""
        from unittest.mock import Mock, patch

        # This test verifies the parameter name is 'category' not 'Category'
        # We don't need to actually instantiate FileStorage, just verify the signature

        import inspect

        from ingenious.files.files_repository import FileStorage

        # Check the __init__ signature has 'category' parameter
        sig = inspect.signature(FileStorage.__init__)
        params = list(sig.parameters.keys())

        assert "category" in params, "FileStorage should have 'category' parameter"
        assert "Category" not in params, "FileStorage should not have 'Category' parameter"

        # Verify the default value
        assert sig.parameters["category"].default == "revisions"


class TestIConversationPatternDeprecation:
    """Test deprecation warnings for IConversationPattern methods."""

    def test_deprecated_methods_exist(self):
        """Test that both old and new method names exist."""
        import inspect

        from ingenious.services.chat_services.multi_agent.service import (
            IConversationPattern,
        )

        # Check that both old and new methods exist
        methods = [name for name, _ in inspect.getmembers(IConversationPattern, inspect.isfunction)]

        # New PEP 8 compliant methods
        assert "get_config" in methods
        assert "get_models" in methods
        assert "get_memory_path" in methods
        assert "get_memory_file" in methods
        assert "maintain_memory" in methods

        # Old deprecated methods (for backward compatibility)
        assert "GetConfig" in methods
        assert "Get_Models" in methods
        assert "Get_Memory_Path" in methods
        assert "Get_Memory_File" in methods
        assert "Maintain_Memory" in methods


class TestIConversationFlowDeprecation:
    """Test deprecation warnings for IConversationFlow methods."""

    def test_deprecated_methods_exist(self):
        """Test that both old and new method names exist."""
        import inspect

        from ingenious.services.chat_services.multi_agent.service import (
            IConversationFlow,
        )

        # Check that both old and new methods exist
        methods = [name for name, _ in inspect.getmembers(IConversationFlow, inspect.isfunction)]

        # New PEP 8 compliant methods
        assert "get_config" in methods
        assert "get_template" in methods
        assert "get_models" in methods
        assert "get_memory_path" in methods
        assert "get_memory_file" in methods
        assert "maintain_memory" in methods

        # Old deprecated methods (for backward compatibility)
        assert "GetConfig" in methods
        assert "Get_Template" in methods
        assert "Get_Models" in methods
        assert "Get_Memory_Path" in methods
        assert "Get_Memory_File" in methods
        assert "Maintain_Memory" in methods
