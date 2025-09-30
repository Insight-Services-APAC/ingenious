"""
Safe dynamic import utilities for Ingenious.

This module provides standardized, safe dynamic import functionality with:
- Comprehensive error handling and logging
- Import caching for performance
- Namespace fallback support for extensions
- Validation of imported modules and classes
- Type safety through protocols
"""

import importlib
import importlib.util
import os
import sys
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingenious.core.structured_logging import get_logger

logger = get_logger(__name__)


class ImportError(Exception):
    """Custom import error with enhanced context."""

    def __init__(
        self,
        message: str,
        module_name: str | None = None,
        class_name: str | None = None,
        attempted_paths: list[str] | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.module_name = module_name
        self.class_name = class_name
        self.attempted_paths = attempted_paths or []
        self.original_error = original_error


class ImportValidationError(Exception):
    """Error raised when imported module/class doesn't meet requirements."""

    pass


class SafeImporter:
    """
    Thread-safe importer with caching, fallback support, and comprehensive error handling.

    Provides standardized dynamic import functionality across the Ingenious codebase
    with support for namespace extensions and proper error reporting.
    """

    def __init__(self) -> None:
        self._module_cache: Dict[str, Any] = {}
        self._class_cache: Dict[str, type] = {}
        self._failed_imports: Dict[str, Exception] = {}
        self._namespaces = self._get_namespaces()

    def _get_namespaces(self) -> List[str]:
        """Get ordered list of namespaces to search for modules."""
        return [
            "ingenious_extensions",
            "ingenious.ingenious_extensions_template",
            "ingenious",
        ]

    def _get_namespace_roots(self) -> List[Path]:
        """Get root directories for namespace searching."""
        working_dir = Path(os.getcwd())
        roots = [
            working_dir / "ingenious_extensions",
            working_dir / "ingenious" / "ingenious_extensions_template",
        ]

        # Add ingenious package root if available
        spec = importlib.util.find_spec("ingenious")
        if spec and spec.origin:
            roots.append(Path(spec.origin).parent)

        return roots

    def _ensure_path_in_sys_path(self, path: Path) -> None:
        """Ensure a path is in sys.path for importing."""
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    def _validate_module(
        self, module: Any, expected_attrs: Optional[List[str]] = None
    ) -> None:
        """Validate that a module meets expected requirements."""
        if module is None:
            raise ImportValidationError("Module is None")

        if expected_attrs:
            missing_attrs = [
                attr for attr in expected_attrs if not hasattr(module, attr)
            ]
            if missing_attrs:
                raise ImportValidationError(
                    f"Module {getattr(module, '__name__', 'unknown')} missing required attributes: {missing_attrs}"
                )

    def _validate_class(
        self,
        cls: type,
        expected_methods: Optional[List[str]] = None,
    ) -> None:
        """Validate that a class meets expected requirements."""
        if not isinstance(cls, type):
            raise ImportValidationError(f"Expected class, got {type(cls)}")

        if expected_methods:
            missing_methods = []
            for method in expected_methods:
                if not hasattr(cls, method) or not callable(getattr(cls, method)):
                    missing_methods.append(method)
            if missing_methods:
                raise ImportValidationError(
                    f"Class {cls.__name__} missing required methods: {missing_methods}"
                )

    @lru_cache(maxsize=128)
    def _find_module_spec(
        self, module_name: str
    ) -> Optional[importlib.machinery.ModuleSpec]:
        """Find module spec with caching."""
        try:
            return importlib.util.find_spec(module_name)
        except (ImportError, ValueError, ModuleNotFoundError):
            return None

    def import_module(
        self,
        module_name: str,
        package: Optional[str] = None,
        expected_attrs: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Any:
        """
        Import a module with comprehensive error handling.

        Args:
            module_name: Name of the module to import
            package: Package for relative imports
            expected_attrs: List of attributes the module must have
            use_cache: Whether to use cached imports

        Returns:
            The imported module

        Raises:
            ImportError: If module cannot be imported or doesn't meet requirements
        """
        cache_key = f"{package}.{module_name}" if package else module_name

        # Check cache first
        if use_cache and cache_key in self._module_cache:
            logger.debug(f"Using cached module: {cache_key}")
            return self._module_cache[cache_key]

        # Check if we've failed to import this before
        if cache_key in self._failed_imports:
            raise self._failed_imports[cache_key]

        attempted_paths: List[str] = []
        original_error: Optional[Exception] = None

        try:
            logger.debug(f"Importing module: {module_name}")

            # Try direct import first
            try:
                # Check if module spec exists first (uses cache)
                spec = self._find_module_spec(module_name)
                if spec is None:
                    raise ModuleNotFoundError(f"No module named '{module_name}'")

                module = importlib.import_module(module_name, package)
                self._validate_module(module, expected_attrs)

                if use_cache:
                    self._module_cache[cache_key] = module

                logger.debug(f"Successfully imported module: {module_name}")
                return module

            except ImportValidationError:
                # Re-raise validation errors immediately without wrapping
                raise
            except (ImportError, ModuleNotFoundError) as e:
                original_error = e
                attempted_paths.append(module_name)
                logger.debug(f"Direct import failed for {module_name}: {e}")

        except ImportValidationError:
            # Re-raise validation errors without wrapping
            raise
        except Exception as e:
            original_error = e
            logger.error(f"Unexpected error importing {module_name}: {e}")

        # Create and cache the error
        error = ImportError(
            f"Failed to import module '{module_name}' after trying paths: {attempted_paths}",
            module_name=module_name,
            attempted_paths=attempted_paths,
            original_error=original_error,
        )

        if use_cache:
            self._failed_imports[cache_key] = error

        raise error

    def import_module_with_fallback(
        self,
        module_name: str,
        expected_attrs: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Any:
        """
        Import a module with namespace fallback support.

        Tries to import from extension namespaces first, then falls back to core ingenious.

        Args:
            module_name: Name of the module (without namespace prefix)
            expected_attrs: List of attributes the module must have
            use_cache: Whether to use cached imports

        Returns:
            The imported module

        Raises:
            ImportError: If module cannot be imported from any namespace
        """
        cache_key = f"fallback:{module_name}"

        # Check cache first
        if use_cache and cache_key in self._module_cache:
            return self._module_cache[cache_key]

        # Check if we've failed to import this before
        if cache_key in self._failed_imports:
            raise self._failed_imports[cache_key]

        attempted_paths: List[str] = []
        original_error: Optional[Exception] = None

        # Try each namespace in order
        for namespace in self._namespaces:
            full_module_name = f"{namespace}.{module_name}"
            attempted_paths.append(full_module_name)

            try:
                logger.debug(f"Trying to import {full_module_name}")

                # Check if module spec exists before trying to import
                if self._find_module_spec(full_module_name):
                    module = self.import_module(
                        full_module_name, expected_attrs=expected_attrs, use_cache=False
                    )

                    if use_cache:
                        self._module_cache[cache_key] = module

                    logger.info(f"Successfully imported {full_module_name}")
                    return module
                else:
                    logger.debug(f"Module spec not found for {full_module_name}")

            except (ImportError, ModuleNotFoundError, ImportValidationError) as e:
                original_error = e
                logger.debug(f"Failed to import {full_module_name}: {e}")
                continue

            except Exception as e:
                original_error = e
                logger.warning(f"Unexpected error importing {full_module_name}: {e}")
                continue

        # Create and cache the error
        error = ImportError(
            f"Failed to import module '{module_name}' from any namespace. Tried: {attempted_paths}",
            module_name=module_name,
            attempted_paths=attempted_paths,
            original_error=original_error,
        )

        if use_cache:
            self._failed_imports[cache_key] = error

        raise error

    def import_class(
        self,
        module_name: str,
        class_name: str,
        expected_methods: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> type:
        """
        Import a class from a module with validation.

        Args:
            module_name: Name of the module containing the class
            class_name: Name of the class to import
            expected_methods: List of methods the class must have
            use_cache: Whether to use cached imports

        Returns:
            The imported class

        Raises:
            ImportError: If class cannot be imported or doesn't meet requirements
        """
        cache_key = f"{module_name}.{class_name}"

        # Check cache first
        if use_cache and cache_key in self._class_cache:
            return self._class_cache[cache_key]

        try:
            # Import the module first
            module = self.import_module(module_name, use_cache=use_cache)

            # Get the class from the module
            if not hasattr(module, class_name):
                raise ImportError(
                    f"Class '{class_name}' not found in module '{module_name}'",
                    module_name=module_name,
                    class_name=class_name,
                )

            cls = getattr(module, class_name)

            if not isinstance(cls, type):
                raise ImportError(
                    f"'{class_name}' is not a class in module '{module_name}'",
                    module_name=module_name,
                    class_name=class_name,
                )

            # Validate the class
            self._validate_class(cls, expected_methods)

            if use_cache:
                self._class_cache[cache_key] = cls

            logger.debug(f"Successfully imported class: {module_name}.{class_name}")
            return cls

        except ImportError:
            raise
        except Exception as e:
            raise ImportError(
                f"Failed to import class '{class_name}' from module '{module_name}': {e}",
                module_name=module_name,
                class_name=class_name,
                original_error=e,
            )

    def import_class_with_fallback(
        self,
        module_name: str,
        class_name: str,
        expected_methods: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> type:
        """
        Import a class with namespace fallback support.

        Args:
            module_name: Name of the module (without namespace prefix)
            class_name: Name of the class to import
            expected_methods: List of methods the class must have
            use_cache: Whether to use cached imports

        Returns:
            The imported class

        Raises:
            ImportError: If class cannot be imported from any namespace
        """
        cache_key = f"fallback:{module_name}.{class_name}"

        # Check cache first
        if use_cache and cache_key in self._class_cache:
            return self._class_cache[cache_key]

        try:
            # Import module with fallback first
            module = self.import_module_with_fallback(module_name, use_cache=use_cache)

            # Get the class from the module
            if not hasattr(module, class_name):
                raise ImportError(
                    f"Class '{class_name}' not found in module '{module_name}'",
                    module_name=module_name,
                    class_name=class_name,
                )

            cls = getattr(module, class_name)

            if not isinstance(cls, type):
                raise ImportError(
                    f"'{class_name}' is not a class in module '{module_name}'",
                    module_name=module_name,
                    class_name=class_name,
                )

            # Validate the class
            self._validate_class(cls, expected_methods)

            if use_cache:
                self._class_cache[cache_key] = cls

            logger.info(
                f"Successfully imported class with fallback: {module_name}.{class_name}"
            )
            return cls

        except ImportError:
            raise
        except Exception as e:
            raise ImportError(
                f"Failed to import class '{class_name}' from module '{module_name}' with fallback: {e}",
                module_name=module_name,
                class_name=class_name,
                original_error=e,
            )

    def validate_dependencies(self, dependencies: List[str]) -> Dict[str, bool]:
        """
        Validate that required dependencies are available.

        Args:
            dependencies: List of module names to check

        Returns:
            Dict mapping dependency names to availability status
        """
        results = {}

        for dep in dependencies:
            try:
                spec = self._find_module_spec(dep)
                results[dep] = spec is not None
                if spec is None:
                    logger.warning(f"Dependency '{dep}' is not available")
                else:
                    logger.debug(f"Dependency '{dep}' is available")
            except Exception as e:
                logger.error(f"Error checking dependency '{dep}': {e}")
                results[dep] = False

        return results

    def clear_cache(self, pattern: Optional[str] = None) -> None:
        """
        Clear import caches.

        Args:
            pattern: Optional pattern to match cache keys to clear
        """
        if pattern:
            # Clear specific pattern
            keys_to_remove = [
                key for key in self._module_cache.keys() if pattern in key
            ]
            for key in keys_to_remove:
                del self._module_cache[key]

            keys_to_remove = [key for key in self._class_cache.keys() if pattern in key]
            for key in keys_to_remove:
                del self._class_cache[key]

            keys_to_remove = [
                key for key in self._failed_imports.keys() if pattern in key
            ]
            for key in keys_to_remove:
                del self._failed_imports[key]
        else:
            # Clear all caches
            self._module_cache.clear()
            self._class_cache.clear()
            self._failed_imports.clear()

        # Also clear the lru_cache
        self._find_module_spec.cache_clear()

        logger.debug(
            "Cleared import caches"
            + (f" matching pattern: {pattern}" if pattern else "")
        )

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the import caches."""
        return {
            "modules_cached": len(self._module_cache),
            "classes_cached": len(self._class_cache),
            "failed_imports": len(self._failed_imports),
            "spec_cache_info": self._find_module_spec.cache_info()._asdict(),
        }


# Global instance for consistent usage across the codebase
_global_importer = SafeImporter()


# Convenience functions for backward compatibility
def import_module_safely(
    module_name: str, expected_attrs: Optional[List[str]] = None
) -> Any:
    """Import a module safely with error handling."""
    return _global_importer.import_module(module_name, expected_attrs=expected_attrs)


def import_class_safely(
    module_name: str, class_name: str, expected_methods: Optional[List[str]] = None
) -> type:
    """Import a class safely with error handling."""
    return _global_importer.import_class(
        module_name, class_name, expected_methods=expected_methods
    )


def import_module_with_fallback(
    module_name: str, expected_attrs: Optional[List[str]] = None
) -> Any:
    """Import a module with namespace fallback support."""
    return _global_importer.import_module_with_fallback(
        module_name, expected_attrs=expected_attrs
    )


def import_class_with_fallback(
    module_name: str, class_name: str, expected_methods: Optional[List[str]] = None
) -> type:
    """Import a class with namespace fallback support."""
    return _global_importer.import_class_with_fallback(
        module_name, class_name, expected_methods=expected_methods
    )


def validate_dependencies(dependencies: List[str]) -> Dict[str, bool]:
    """Validate that required dependencies are available."""
    return _global_importer.validate_dependencies(dependencies)


def clear_import_cache(pattern: Optional[str] = None) -> None:
    """Clear import caches."""
    _global_importer.clear_cache(pattern)


def get_import_stats() -> Dict[str, Any]:
    """Get import cache statistics."""
    return _global_importer.get_cache_stats()


# Deprecation warnings for old functions
def _deprecated_import_warning(old_func: str, new_func: str) -> None:
    """Issue deprecation warning for old import functions."""
    warnings.warn(
        f"{old_func} is deprecated. Use {new_func} from ingenious.utils.imports instead.",
        DeprecationWarning,
        stacklevel=3,
    )
