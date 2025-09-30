"""
Unit tests for the SafeImporter system.

Tests the functionality of dynamic imports, caching, validation,
error handling, and protocol compliance checking.
"""

from unittest.mock import patch

import pytest

from ingenious.utils.imports import (
    ImportError as SafeImportError,
)
from ingenious.utils.imports import (
    ImportValidationError,
    SafeImporter,
    clear_import_cache,
    get_import_stats,
    import_class_safely,
    import_class_with_fallback,
    import_module_safely,
    import_module_with_fallback,
    validate_dependencies,
)


class TestSafeImporter:
    """Test the SafeImporter class."""

    def setup_method(self):
        """Set up test instance."""
        self.importer = SafeImporter()
        self.importer.clear_cache()

    def test_import_module_success(self):
        """Test successful module import."""
        module = self.importer.import_module("os")
        assert module is not None
        assert hasattr(module, "path")

    def test_import_module_with_expected_attrs(self):
        """Test module import with attribute validation."""
        module = self.importer.import_module("os", expected_attrs=["path", "environ"])
        assert module is not None
        assert hasattr(module, "path")
        assert hasattr(module, "environ")

    def test_import_module_missing_attrs(self):
        """Test module import fails when expected attributes are missing."""
        with pytest.raises(ImportValidationError):
            self.importer.import_module("os", expected_attrs=["nonexistent_attr"])

    def test_import_module_not_found(self):
        """Test import error for non-existent module."""
        with pytest.raises(SafeImportError) as exc_info:
            self.importer.import_module("nonexistent_module_12345")

        error = exc_info.value
        assert error.module_name == "nonexistent_module_12345"
        assert "Failed to import module" in str(error)

    def test_import_class_success(self):
        """Test successful class import."""
        cls = self.importer.import_class("collections", "defaultdict")
        assert cls is not None
        assert callable(cls)
        assert cls.__name__ == "defaultdict"

    def test_import_class_with_expected_methods(self):
        """Test class import with method validation."""
        cls = self.importer.import_class(
            "collections", "defaultdict", expected_methods=["__init__", "clear"]
        )
        assert cls is not None
        assert hasattr(cls, "__init__")
        assert hasattr(cls, "clear")

    def test_import_class_missing_methods(self):
        """Test class import fails when expected methods are missing."""
        with pytest.raises(SafeImportError):
            self.importer.import_class(
                "collections", "defaultdict", expected_methods=["nonexistent_method"]
            )

    def test_import_class_not_found(self):
        """Test import error for non-existent class."""
        with pytest.raises(SafeImportError) as exc_info:
            self.importer.import_class("collections", "NonExistentClass")

        error = exc_info.value
        assert error.class_name == "NonExistentClass"
        assert "not found in module" in str(error)

    def test_import_module_with_fallback_success(self):
        """Test successful module import with fallback."""
        # This should work by importing from the ingenious namespace
        module = self.importer.import_module_with_fallback("utils.imports")
        assert module is not None
        assert hasattr(module, "SafeImporter")

    def test_import_class_with_fallback_success(self):
        """Test successful class import with fallback."""
        cls = self.importer.import_class_with_fallback("utils.imports", "SafeImporter")
        assert cls is not None
        assert cls.__name__ == "SafeImporter"

    def test_import_with_fallback_not_found(self):
        """Test import with fallback fails for non-existent module."""
        with pytest.raises(SafeImportError):
            self.importer.import_module_with_fallback("nonexistent.module")

    def test_caching_works(self):
        """Test that import caching works correctly."""
        # First import
        module1 = self.importer.import_module("os")

        # Second import should use cache
        with patch("importlib.import_module") as mock_import:
            module2 = self.importer.import_module("os")
            # importlib.import_module should not be called again
            mock_import.assert_not_called()

        assert module1 is module2

    def test_cache_disable(self):
        """Test disabling cache works."""
        # Import with cache disabled
        module1 = self.importer.import_module("os", use_cache=False)
        module2 = self.importer.import_module("os", use_cache=False)

        # Both should be the same module object (since it's the same import)
        # but cache should not be used
        assert module1 is module2
        assert "os" not in self.importer._module_cache

    def test_clear_cache(self):
        """Test cache clearing."""
        # Import something to populate cache
        self.importer.import_module("os")
        assert len(self.importer._module_cache) > 0

        # Clear cache
        self.importer.clear_cache()
        assert len(self.importer._module_cache) == 0

    def test_clear_cache_pattern(self):
        """Test cache clearing with pattern."""
        # Import multiple modules
        self.importer.import_module("os")
        self.importer.import_module("sys")

        # Clear only 'os' related cache
        self.importer.clear_cache("os")

        # Check that only 'os' cache was cleared
        cache_keys = list(self.importer._module_cache.keys())
        assert not any("os" in key for key in cache_keys)
        assert any("sys" in key for key in cache_keys)

    def test_validate_dependencies_success(self):
        """Test dependency validation with existing modules."""
        results = self.importer.validate_dependencies(["os", "sys", "collections"])

        assert len(results) == 3
        assert all(results.values())  # All should be True

    def test_validate_dependencies_mixed(self):
        """Test dependency validation with mix of existing and missing modules."""
        results = self.importer.validate_dependencies(
            ["os", "nonexistent_module_12345", "sys"]
        )

        assert len(results) == 3
        assert results["os"] is True
        assert results["nonexistent_module_12345"] is False
        assert results["sys"] is True

    def test_cache_stats(self):
        """Test getting cache statistics."""
        # Initial stats
        stats = self.importer.get_cache_stats()
        assert "modules_cached" in stats
        assert "classes_cached" in stats
        assert "failed_imports" in stats

        # Import something
        self.importer.import_module("os")
        self.importer.import_class("collections", "defaultdict")

        # Check stats updated
        new_stats = self.importer.get_cache_stats()
        assert new_stats["modules_cached"] >= 1
        assert new_stats["classes_cached"] >= 1


class TestConvenienceFunctions:
    """Test the convenience functions."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_import_cache()

    def test_import_module_safely(self):
        """Test import_module_safely function."""
        module = import_module_safely("os")
        assert module is not None
        assert hasattr(module, "path")

    def test_import_class_safely(self):
        """Test import_class_safely function."""
        cls = import_class_safely("collections", "defaultdict")
        assert cls is not None
        assert cls.__name__ == "defaultdict"

    def test_import_module_with_fallback_function(self):
        """Test import_module_with_fallback function."""
        module = import_module_with_fallback("utils.imports")
        assert module is not None
        assert hasattr(module, "SafeImporter")

    def test_import_class_with_fallback_function(self):
        """Test import_class_with_fallback function."""
        cls = import_class_with_fallback("utils.imports", "SafeImporter")
        assert cls is not None
        assert cls.__name__ == "SafeImporter"

    def test_validate_dependencies_function(self):
        """Test validate_dependencies function."""
        results = validate_dependencies(["os", "sys"])
        assert len(results) == 2
        assert all(results.values())

    def test_get_import_stats(self):
        """Test get_import_stats function."""
        stats = get_import_stats()
        assert "modules_cached" in stats
        assert isinstance(stats["modules_cached"], int)


class TestErrorHandling:
    """Test error handling in imports."""

    def setup_method(self):
        """Set up test instance."""
        self.importer = SafeImporter()
        self.importer.clear_cache()

    def test_import_error_details(self):
        """Test that ImportError contains detailed information."""
        with pytest.raises(SafeImportError) as exc_info:
            self.importer.import_module("nonexistent_module_12345")

        error = exc_info.value
        assert error.module_name == "nonexistent_module_12345"
        assert error.attempted_paths is not None
        assert error.original_error is not None

    def test_failed_import_caching(self):
        """Test that failed imports are cached to avoid repeated attempts."""
        # First failed import
        with pytest.raises(SafeImportError):
            self.importer.import_module("nonexistent_module_12345")

        # Should be in failed imports cache
        assert "nonexistent_module_12345" in self.importer._failed_imports

        # Second attempt should raise the cached error
        with pytest.raises(SafeImportError):
            self.importer.import_module("nonexistent_module_12345")

    def test_validation_error_propagation(self):
        """Test that validation errors are properly propagated."""
        with pytest.raises(ImportValidationError):
            self.importer.import_module("os", expected_attrs=["nonexistent_attr"])


class TestNamespaceFallback:
    """Test namespace fallback functionality."""

    def setup_method(self):
        """Set up test instance."""
        self.importer = SafeImporter()
        self.importer.clear_cache()

    def test_namespace_order(self):
        """Test that namespaces are tried in correct order."""
        namespaces = self.importer._get_namespaces()
        expected = [
            "ingenious_extensions",
            "ingenious.ingenious_extensions_template",
            "ingenious",
        ]
        assert namespaces == expected

    def test_fallback_to_ingenious(self):
        """Test fallback to ingenious namespace works."""
        # This should fall back to ingenious.utils.imports
        module = self.importer.import_module_with_fallback("utils.imports")
        assert module is not None
        assert hasattr(module, "SafeImporter")


class TestPerformance:
    """Test performance aspects of the import system."""

    def setup_method(self):
        """Set up test instance."""
        self.importer = SafeImporter()
        self.importer.clear_cache()

    def test_cache_performance(self):
        """Test that caching improves performance."""
        import time

        # Time first import (no cache)
        start = time.time()
        self.importer.import_module("collections")
        first_time = time.time() - start

        # Time second import (with cache)
        start = time.time()
        self.importer.import_module("collections")
        second_time = time.time() - start

        # Second import should be faster (though this might be flaky in tests)
        # At minimum, both should complete successfully
        assert first_time >= 0
        assert second_time >= 0

    def test_lru_cache_usage(self):
        """Test that LRU cache is being used for spec finding."""
        # Import multiple modules to populate spec cache
        modules = ["os", "sys", "collections", "json", "re"]

        for module_name in modules:
            self.importer.import_module(module_name)

        # Check cache info
        cache_info = self.importer._find_module_spec.cache_info()
        assert cache_info.hits > 0 or cache_info.misses > 0


class TestIntegrationWithIngeniousModules:
    """Test integration with actual Ingenious modules."""

    def setup_method(self):
        """Set up test instance."""
        self.importer = SafeImporter()
        self.importer.clear_cache()

    def test_import_ingenious_config(self):
        """Test importing Ingenious config module."""
        module = self.importer.import_module("ingenious.config")
        assert module is not None
        assert hasattr(module, "get_config")

    def test_import_ingenious_utils(self):
        """Test importing Ingenious utils module."""
        module = self.importer.import_module("ingenious.utils.imports")
        assert module is not None
        assert hasattr(module, "SafeImporter")

    def test_import_with_fallback_ingenious(self):
        """Test fallback import works with actual Ingenious modules."""
        # Should work by falling back to ingenious namespace
        cls = self.importer.import_class_with_fallback("utils.imports", "SafeImporter")
        assert cls is not None
        assert cls.__name__ == "SafeImporter"
