"""
Namespace utilities for dynamic imports and workflow discovery.

This module provides utilities for working with namespaces, discovering workflows,
and handling dynamic imports across the Ingenious ecosystem with proper fallback support.
"""

import os
import pkgutil
from pathlib import Path
from sysconfig import get_paths
from typing import Any, Dict, List, Optional, Set

from ingenious.core.structured_logging import get_logger
from ingenious.utils.imports import SafeImporter

logger = get_logger(__name__)

# Global importer instance
_importer = SafeImporter()


def normalize_workflow_name(workflow_name: str) -> str:
    """
    Normalize workflow names to support both hyphenated and underscored formats.
    Converts hyphens to underscores for module path compatibility.

    Args:
        workflow_name (str): The workflow name (e.g., "bike-insights" or "bike_insights")

    Returns:
        str: The normalized workflow name with underscores (e.g., "bike_insights")
    """
    if not workflow_name:
        return workflow_name
    return workflow_name.replace("-", "_").lower()


def print_namespace_modules(namespace: str) -> None:
    """
    Print all modules found in a namespace.

    Args:
        namespace: The namespace to explore
    """
    try:
        package = _importer.import_module(namespace)
        if hasattr(package, "__path__"):
            for module_info in pkgutil.iter_modules(package.__path__):
                print(f"Found module: {module_info.name}")
        else:
            print(f"{namespace} is not a package. Importing now...")
    except Exception as e:
        logger.error(f"Error exploring namespace {namespace}: {e}")


def get_dir_roots() -> List[Path]:
    """
    Retrieve a list of directory paths that are considered as root directories for the project.

    The function checks potential locations for the root directories:
    1. The 'ingenious_extensions' folder in the current working directory.
    2. The 'ingenious_extensions_templates' folder in the 'ingenious' directory within the current working directory.
    3. The 'ingenious' folder in the site-packages directory of the current Python environment.

    Returns:
        list: A list of Path objects representing the root directories.
    """
    working_dir = Path(os.getcwd())

    # First try the project extensions folder.. this will override all else
    extensions_dir = working_dir / "ingenious_extensions"

    # next try the extensions template folder.. this will only exist if in development version
    extensions_template_dir = (
        working_dir / "ingenious" / "ingenious_extensions_template"
    )

    # finally try the ingenious folder in pip install location
    try:
        ingenious_dir = Path(get_paths()["purelib"]) / "ingenious"
    except Exception:
        # Fallback if get_paths() fails
        ingenious_dir = Path(__file__).parent.parent

    return [extensions_dir, extensions_template_dir, ingenious_dir]


def get_namespaces(include_builtin: bool = True) -> List[str]:
    """
    Get ordered list of namespaces to search for modules.

    Args:
        include_builtin: Whether to include built-in workflows from 'ingenious' namespace

    Returns:
        List of namespace strings in priority order
    """
    namespaces = [
        "ingenious_extensions",
        "ingenious.ingenious_extensions_template",
    ]

    if include_builtin:
        namespaces.append("ingenious")

    return namespaces


def get_file_from_namespace_with_fallback(
    module_name: str, file_name: str
) -> Optional[str]:
    """
    Try to read a file from the Ingenious Extensions package and fall back to the Ingenious package if not found.

    Args:
        module_name (str): The name of the module to import (excluding the top level of ingenious or ingenious_extensions).
        file_name (str): The name of the file to import.

    Returns:
        File content as string, or None if not found
    """
    dirs = [(d / Path(module_name) / Path(file_name)) for d in get_dir_roots()]

    for dir_path in dirs:
        if dir_path.exists():
            try:
                with open(dir_path, "r", encoding="utf-8") as file:
                    return file.read()
            except Exception as e:
                logger.warning(f"Error reading file {dir_path}: {e}")
                continue

    logger.warning(f"File {file_name} not found in module {module_name}")
    return None


def get_path_from_namespace_with_fallback(path: str) -> Optional[Path]:
    """
    Try to get a path from the Ingenious Extensions package and fall back to the Ingenious package if not found.

    Args:
        path (str): The relative path to search for

    Returns:
        Path object if found, None otherwise
    """
    dirs = [(d / Path(path)) for d in get_dir_roots()]

    for dir_path in dirs:
        if dir_path.exists():
            return dir_path

    logger.warning(f"Path {path} not found in any namespace")
    return None


def get_inbuilt_api_routes() -> Optional[Path]:
    """
    Retrieve the path to in-built API routes from the Ingenious package.

    Returns:
        Path object to the API routes directory, or None if not found
    """
    working_dir = Path(os.getcwd()) / "ingenious" / "api" / "routes"

    try:
        install_dir = Path(get_paths()["purelib"]) / "ingenious" / "api" / "routes"
    except Exception:
        install_dir = Path(__file__).parent.parent / "api" / "routes"

    for dir_path in [working_dir, install_dir]:
        if dir_path.exists():
            return dir_path

    logger.warning("In-built API routes directory not found")
    return None


class WorkflowDiscovery:
    """Enhanced workflow discovery with validation and caching."""

    def __init__(self) -> None:
        self._workflow_cache: Optional[List[str]] = None
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}

    def discover_workflows(
        self, force_refresh: bool = False, include_builtin: bool = True
    ) -> List[str]:
        """
        Dynamically discover all available workflows from all namespaces.

        This function searches through core Ingenious and extension namespaces
        to find available workflow modules with proper validation.

        Args:
            force_refresh: Whether to force refresh the cached results
            include_builtin: Whether to include built-in workflows from 'ingenious' namespace

        Returns:
            list: A list of workflow names (normalized with underscores)
        """
        # Use cache key that includes the include_builtin parameter
        cache_key = f"workflows_{include_builtin}"
        if not hasattr(self, "_workflow_caches"):
            self._workflow_caches = {}

        if cache_key in self._workflow_caches and not force_refresh:
            return self._workflow_caches[cache_key]

        workflows: Set[str] = set()
        namespaces = get_namespaces(include_builtin=include_builtin)

        for namespace in namespaces:
            try:
                # Try to import the conversation flows package
                flows_module_name = (
                    f"{namespace}.services.chat_services.multi_agent.conversation_flows"
                )
                logger.debug(f"Searching for workflows in {flows_module_name}")

                try:
                    flows_package = _importer.import_module(flows_module_name)

                    if hasattr(flows_package, "__path__"):
                        # Iterate through all modules in the conversation_flows package
                        for module_info in pkgutil.iter_modules(flows_package.__path__):
                            workflow_name = module_info.name
                            logger.debug(f"Found potential workflow: {workflow_name}")

                            # Try to import and validate the workflow module
                            if self._validate_workflow(
                                flows_module_name, workflow_name
                            ):
                                workflows.add(workflow_name)
                                logger.debug(f"Confirmed workflow: {workflow_name}")

                except Exception as e:
                    logger.debug(f"No conversation flows found in {namespace}: {e}")
                    continue

            except Exception as e:
                logger.debug(f"Error searching namespace {namespace}: {e}")
                continue

        # Convert to sorted list and cache
        result = sorted(list(workflows))
        self._workflow_caches[cache_key] = result

        # Also update the old cache for backward compatibility
        if include_builtin:
            self._workflow_cache = result

        return result

    def _validate_workflow(self, flows_module_name: str, workflow_name: str) -> bool:
        """
        Validate that a workflow module contains a proper ConversationFlow class.

        Args:
            flows_module_name: Base module name for flows
            workflow_name: Name of the specific workflow

        Returns:
            True if workflow is valid
        """
        try:
            workflow_module_name = (
                f"{flows_module_name}.{workflow_name}.{workflow_name}"
            )
            workflow_module = _importer.import_module(workflow_module_name)

            # Check if it has a ConversationFlow class
            if hasattr(workflow_module, "ConversationFlow"):
                conversation_flow_class = getattr(workflow_module, "ConversationFlow")

                # Validate against protocol
                try:
                    # Check basic protocol compliance - workflows can use either method name
                    required_methods = [
                        "get_conversation_response",
                        "get_chat_response",
                    ]
                    has_required_method = False
                    for method in required_methods:
                        if hasattr(conversation_flow_class, method):
                            has_required_method = True
                            break

                    if not has_required_method:
                        logger.debug(
                            f"Workflow {workflow_name} missing required method. "
                            f"Must have one of: {required_methods}"
                        )
                        return False

                    return True

                except Exception as e:
                    logger.debug(f"Protocol validation failed for {workflow_name}: {e}")
                    return False
            else:
                logger.debug(f"Workflow {workflow_name} missing ConversationFlow class")
                return False

        except Exception as e:
            logger.debug(f"Skipping {workflow_name} - not a valid workflow: {e}")
            return False

    def get_workflow_metadata(self, workflow_name: str) -> Dict[str, Any]:
        """
        Get metadata for a specific workflow.

        Args:
            workflow_name (str): The workflow name

        Returns:
            dict: Workflow metadata including description, category, etc.
        """
        if workflow_name in self._metadata_cache:
            return self._metadata_cache[workflow_name]

        # Default metadata structure
        default_metadata = {
            "description": "Custom workflow",
            "category": "Custom Workflow",
            "required_config": ["models", "chat_service"],
            "optional_config": [],
            "external_services": ["Azure OpenAI"],
        }

        # Define known workflow metadata
        known_workflows = {
            "classification_agent": {
                "description": "Route input to specialized agents based on content",
                "category": "Minimal Configuration",
                "required_config": ["models", "chat_service"],
                "optional_config": [],
                "external_services": ["Azure OpenAI"],
            },
            "bike_insights": {
                "description": "Sample domain-specific workflow for bike sales analysis",
                "category": "Minimal Configuration",
                "required_config": ["models", "chat_service"],
                "optional_config": [],
                "external_services": ["Azure OpenAI"],
            },
            "knowledge_base_agent": {
                "description": "Search and retrieve information from knowledge bases using ChromaDB",
                "category": "Minimal Configuration",
                "required_config": ["models", "chat_service"],
                "optional_config": ["azure_search_services"],
                "external_services": ["Azure OpenAI"],
            },
            "sql_manipulation_agent": {
                "description": "Execute SQL queries based on natural language",
                "category": "Database Required",
                "required_config": ["models", "chat_service"],
                "optional_config": ["azure_sql_services", "local_sql_db"],
                "external_services": ["Azure OpenAI", "Database (Azure SQL or SQLite)"],
            },
            "submission_over_criteria": {
                "description": "Evaluate submissions against specified criteria using multi-agent analysis",
                "category": "Custom Workflow",
                "required_config": ["models", "chat_service"],
                "optional_config": ["azure_blob_storage"],
                "external_services": [
                    "Azure OpenAI",
                    "Azure Blob Storage (for templates)",
                ],
            },
        }

        metadata = known_workflows.get(workflow_name, default_metadata)
        self._metadata_cache[workflow_name] = metadata
        return metadata

    def clear_cache(self) -> None:
        """Clear workflow discovery caches."""
        self._workflow_cache = None
        self._metadata_cache.clear()


# Global workflow discovery instance
_workflow_discovery = WorkflowDiscovery()


# Public API functions
def discover_workflows(
    force_refresh: bool = False, include_builtin: bool = True
) -> List[str]:
    """Discover all available workflows.

    Args:
        force_refresh: Whether to force refresh the cached results
        include_builtin: Whether to include built-in workflows from 'ingenious' namespace
    """
    return _workflow_discovery.discover_workflows(force_refresh, include_builtin)


def get_workflow_metadata(workflow_name: str) -> Dict[str, Any]:
    """Get metadata for a specific workflow."""
    return _workflow_discovery.get_workflow_metadata(workflow_name)
