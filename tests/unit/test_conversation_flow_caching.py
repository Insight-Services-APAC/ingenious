"""Unit tests for conversation flow class import caching."""

from unittest.mock import Mock, patch

import pytest


class TestConversationFlowCaching:
    """Test cases for conversation flow class caching."""

    def test_get_conversation_flow_class_caches_imports(self):
        """Test that get_conversation_flow_class caches imported classes."""
        # Mock openai import to avoid dependency issues in tests
        with patch.dict(
            "sys.modules", {"openai": Mock(), "openai.types": Mock(), "openai.types.chat": Mock()}
        ):
            from ingenious.services.chat_services.multi_agent.service import (
                get_conversation_flow_class,
            )

            # Clear the cache before testing
            get_conversation_flow_class.cache_clear()

            with patch(
                "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback"
            ) as mock_import:
                mock_class = Mock()
                mock_import.return_value = mock_class

                # First call should import
                result1 = get_conversation_flow_class("test.module", "TestClass")
                assert result1 == mock_class
                assert mock_import.call_count == 1

                # Second call with same arguments should use cache
                result2 = get_conversation_flow_class("test.module", "TestClass")
                assert result2 == mock_class
                assert mock_import.call_count == 1  # Should still be 1, not 2

                # Third call with same arguments should still use cache
                result3 = get_conversation_flow_class("test.module", "TestClass")
                assert result3 == mock_class
                assert mock_import.call_count == 1  # Should still be 1

    def test_get_conversation_flow_class_different_modules(self):
        """Test that different module names create separate cache entries."""
        with patch.dict(
            "sys.modules", {"openai": Mock(), "openai.types": Mock(), "openai.types.chat": Mock()}
        ):
            from ingenious.services.chat_services.multi_agent.service import (
                get_conversation_flow_class,
            )

            # Clear the cache before testing
            get_conversation_flow_class.cache_clear()

            with patch(
                "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback"
            ) as mock_import:
                mock_class1 = Mock()
                mock_class2 = Mock()
                mock_import.side_effect = [mock_class1, mock_class2]

                # First call with module1
                result1 = get_conversation_flow_class("test.module1", "TestClass")
                assert result1 == mock_class1
                assert mock_import.call_count == 1

                # Second call with module2 should import again
                result2 = get_conversation_flow_class("test.module2", "TestClass")
                assert result2 == mock_class2
                assert mock_import.call_count == 2

                # Third call with module1 should use cache
                result3 = get_conversation_flow_class("test.module1", "TestClass")
                assert result3 == mock_class1
                assert mock_import.call_count == 2  # Should still be 2

    def test_get_conversation_flow_class_cache_info(self):
        """Test that cache info is accessible and shows correct statistics."""
        with patch.dict(
            "sys.modules", {"openai": Mock(), "openai.types": Mock(), "openai.types.chat": Mock()}
        ):
            from ingenious.services.chat_services.multi_agent.service import (
                get_conversation_flow_class,
            )

            # Clear the cache before testing
            get_conversation_flow_class.cache_clear()

            with patch(
                "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback"
            ) as mock_import:
                mock_class = Mock()
                mock_import.return_value = mock_class

                # Check initial cache info
                cache_info = get_conversation_flow_class.cache_info()
                assert cache_info.hits == 0
                assert cache_info.misses == 0

                # First call should be a miss
                get_conversation_flow_class("test.module", "TestClass")
                cache_info = get_conversation_flow_class.cache_info()
                assert cache_info.hits == 0
                assert cache_info.misses == 1

                # Second call should be a hit
                get_conversation_flow_class("test.module", "TestClass")
                cache_info = get_conversation_flow_class.cache_info()
                assert cache_info.hits == 1
                assert cache_info.misses == 1

                # Third call should be another hit
                get_conversation_flow_class("test.module", "TestClass")
                cache_info = get_conversation_flow_class.cache_info()
                assert cache_info.hits == 2
                assert cache_info.misses == 1

    def test_get_conversation_flow_class_cache_maxsize(self):
        """Test that cache respects maxsize=32 limit."""
        with patch.dict(
            "sys.modules", {"openai": Mock(), "openai.types": Mock(), "openai.types.chat": Mock()}
        ):
            from ingenious.services.chat_services.multi_agent.service import (
                get_conversation_flow_class,
            )

            # Clear the cache before testing
            get_conversation_flow_class.cache_clear()

            with patch(
                "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback"
            ) as mock_import:
                mock_class = Mock()
                mock_import.return_value = mock_class

                # Import 33 different modules (more than maxsize=32)
                for i in range(33):
                    get_conversation_flow_class(f"test.module{i}", "TestClass")

                # Check cache info - should have evicted at least one entry
                cache_info = get_conversation_flow_class.cache_info()
                assert cache_info.currsize <= 32

    def test_get_conversation_flow_class_propagates_errors(self):
        """Test that import errors are propagated correctly."""
        with patch.dict(
            "sys.modules", {"openai": Mock(), "openai.types": Mock(), "openai.types.chat": Mock()}
        ):
            from ingenious.services.chat_services.multi_agent.service import (
                get_conversation_flow_class,
            )

            # Clear the cache before testing
            get_conversation_flow_class.cache_clear()

            with patch(
                "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback"
            ) as mock_import:
                mock_import.side_effect = ImportError("Module not found")

                with pytest.raises(ImportError, match="Module not found"):
                    get_conversation_flow_class("test.nonexistent", "TestClass")
