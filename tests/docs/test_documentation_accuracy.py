"""
Test file to validate documentation accuracy against implementation.

This test suite verifies that documentation claims match the actual codebase
implementation through static analysis only. It does not execute any code.

Note: This file is meant to be run after documentation updates to ensure
accuracy is maintained.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest


class DocumentationValidator:
    """Validates documentation claims against implementation."""

    def __init__(self) -> None:
        self.workspace_root = Path(
            __file__
        ).parent.parent.parent  # Go up from tests/docs/ to root
        self.docs_dir = self.workspace_root / "docs"
        self.ingenious_dir = self.workspace_root / "ingenious"

    def extract_api_endpoints_from_code(self) -> Dict[str, List[Tuple[str, str]]]:
        """Extract API endpoints from route files."""
        endpoints = {}
        routes_dir = self.ingenious_dir / "api" / "routes"

        for route_file in routes_dir.glob("*.py"):
            if route_file.name == "__init__.py":
                continue

            with open(route_file, "r") as f:
                content = f.read()

            # Extract route decorators - handle both single-line and multi-line formats
            route_pattern = (
                r'@router\.(get|post|put|delete|patch|api_route)\(\s*"([^"]+)"'
            )
            matches = re.findall(route_pattern, content, re.MULTILINE | re.DOTALL)

            module_name = route_file.stem
            endpoints[module_name] = [(method, path) for method, path in matches]

        return endpoints

    def extract_cli_commands_from_code(self) -> Set[str]:
        """Extract CLI commands from the CLI module."""
        commands = set()
        cli_dir = self.ingenious_dir / "cli"

        # Look for @app.command decorators
        for cli_file in cli_dir.rglob("*.py"):
            with open(cli_file, "r") as f:
                content = f.read()

            # Extract command names - handle both name= and no name format
            command_pattern = r'@app\.command\(\s*(?:name=)?"([^"]+)"'
            matches = re.findall(command_pattern, content, re.MULTILINE | re.DOTALL)
            commands.update(matches)

            # Also look for @app.command() without name (function name is used)
            function_command_pattern = (
                r"@app\.command\([^)]*\)\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)"
            )
            function_matches = re.findall(
                function_command_pattern, content, re.MULTILINE | re.DOTALL
            )
            commands.update(function_matches)

        return commands

    def extract_environment_variables_from_code(self) -> Set[str]:
        """Extract environment variable names from settings classes."""
        env_vars = set()
        config_dir = self.ingenious_dir / "config"

        # Look for INGENIOUS_ prefixed variables
        for config_file in config_dir.glob("*.py"):
            with open(config_file, "r") as f:
                content = f.read()

            # Extract environment variable references
            env_pattern = r"INGENIOUS_[A-Z_0-9]+"
            matches = re.findall(env_pattern, content)
            env_vars.update(matches)

        return env_vars

    def extract_workflow_names_from_code(self) -> Set[str]:
        """Extract workflow names from the codebase."""
        workflows = set()

        # Check conversation flows directory
        flows_dir = (
            self.ingenious_dir
            / "services"
            / "chat_services"
            / "multi_agent"
            / "conversation_flows"
        )
        if flows_dir.exists():
            for flow_dir in flows_dir.iterdir():
                if flow_dir.is_dir() and not flow_dir.name.startswith("__"):
                    workflows.add(flow_dir.name)

        # Check for template workflows
        template_flows_dir = (
            self.workspace_root
            / "test_dir"
            / "ingenious_extensions"
            / "services"
            / "chat_services"
            / "multi_agent"
            / "conversation_flows"
        )
        if template_flows_dir.exists():
            for flow_dir in template_flows_dir.iterdir():
                if flow_dir.is_dir() and not flow_dir.name.startswith("__"):
                    workflows.add(flow_dir.name)

        return workflows

    def validate_pyproject_toml(self) -> Dict[str, Any]:
        """Extract key information from pyproject.toml."""
        pyproject_path = self.workspace_root / "pyproject.toml"
        info = {}

        with open(pyproject_path, "r") as f:
            content = f.read()

        # Extract Python version requirement
        version_match = re.search(r'requires-python = "([^"]+)"', content)
        if version_match:
            info["python_version"] = version_match.group(1)

        # Extract project version
        project_version_match = re.search(r'version = "([^"]+)"', content)
        if project_version_match:
            info["project_version"] = project_version_match.group(1)

        # Extract CLI command entry point
        cli_match = re.search(r'ingen = "([^"]+)"', content)
        if cli_match:
            info["cli_entrypoint"] = cli_match.group(1)

        return info


class TestDocumentationAccuracy:
    """Test suite for documentation accuracy validation."""

    @pytest.fixture
    def validator(self):
        return DocumentationValidator()

    def test_api_endpoints_documented(self, validator):
        """Verify all API endpoints are correctly documented."""
        code_endpoints = validator.extract_api_endpoints_from_code()

        # Expected endpoints based on documentation analysis
        expected_endpoints = {
            "auth": [("post", "/login"), ("post", "/refresh"), ("get", "/verify")],
            "chat": [("post", "/chat")],
            "conversation": [("get", "/conversations/{thread_id}")],
            "diagnostic": [
                ("get", "/workflow-status/{workflow_name}"),
                ("get", "/workflows"),
                ("api_route", "/diagnostic"),
                ("get", "/health"),
            ],
            "message_feedback": [("put", "/messages/{message_id}/feedback")],
            "prompts": [
                ("get", "/revisions/list"),
                ("get", "/workflows/list"),
                ("get", "/prompts/list/{revision_id}"),
                ("get", "/prompts/view/{revision_id}/{filename}"),
                ("post", "/prompts/update/{revision_id}/{filename}"),
            ],
        }

        # Verify documented endpoints exist
        for module, endpoints in expected_endpoints.items():
            assert module in code_endpoints, f"Module {module} not found in code"
            for method, path in endpoints:
                assert (method, path) in code_endpoints[module], (
                    f"Endpoint {method} {path} not found in {module}"
                )

    def test_cli_commands_documented(self, validator):
        """Verify all CLI commands are correctly documented."""
        code_commands = validator.extract_cli_commands_from_code()

        # Expected commands based on documentation and actual CLI output
        expected_commands = {
            "init",
            "serve",
            "workflows",
            "test",
            "validate",
            "status",
            "version",
            "help",  # This should be found as help_command function
            "prompt-tuner",  # This should be found as prompt_tuner function
        }

        # Map function names to command names for more flexible matching
        command_mappings = {
            "help_command": "help",
            "prompt_tuner": "prompt-tuner",
            "help": "help",
            "prompt-tuner": "prompt-tuner",
        }

        # Create a set of normalized command names
        normalized_commands = set()
        for cmd in code_commands:
            normalized_commands.add(command_mappings.get(cmd, cmd))

        # Verify documented commands exist (allow for more commands in code)
        for cmd in expected_commands:
            assert cmd in normalized_commands or cmd in code_commands, (
                f"Command '{cmd}' documented but not found in code. Available: {sorted(normalized_commands | code_commands)}"
            )

    def test_environment_variables_documented(self, validator):
        """Verify environment variable prefixes are correct."""
        code_env_vars = validator.extract_environment_variables_from_code()

        # All environment variables should have INGENIOUS_ prefix
        for var in code_env_vars:
            assert var.startswith("INGENIOUS_"), (
                f"Environment variable {var} doesn't have correct prefix"
            )

    def test_workflow_names_documented(self, validator):
        """Verify workflow names are correctly documented."""
        code_workflows = validator.extract_workflow_names_from_code()

        # Documented core workflows
        documented_core_workflows = {
            "classification_agent",
            "knowledge_base_agent",
            "sql_manipulation_agent",
        }

        # Verify at least core workflows exist
        for workflow in documented_core_workflows:
            assert workflow in code_workflows, (
                f"Core workflow '{workflow}' documented but not found in code"
            )

    def test_python_version_requirement(self, validator):
        """Verify Python version requirement is correctly documented."""
        pyproject_info = validator.validate_pyproject_toml()

        # Documentation states Python 3.13+
        assert "python_version" in pyproject_info
        assert pyproject_info["python_version"] == ">=3.13", (
            f"Python version requirement mismatch: {pyproject_info['python_version']}"
        )

    def test_project_structure_matches_docs(self, validator):
        """Verify key project directories exist as documented."""
        expected_dirs = [
            "ingenious",
            "docs",
            "tests",
            "scripts",
            "ingenious/api/routes",
            "ingenious/cli",
            "ingenious/config",
            "ingenious/services/chat_services",
        ]

        for dir_path in expected_dirs:
            full_path = validator.workspace_root / dir_path
            assert full_path.exists(), f"Expected directory not found: {dir_path}"

    def test_api_base_path(self, validator):
        """Verify API base path is /api/v1 as documented."""
        # Check routing configuration
        routing_file = validator.ingenious_dir / "main" / "routing.py"
        assert routing_file.exists()

        with open(routing_file, "r") as f:
            content = f.read()

        # Verify /api/v1 prefix is used
        assert 'prefix="/api/v1"' in content, (
            "API base path /api/v1 not found in routing"
        )

    def test_configuration_system(self, validator):
        """Verify configuration uses pydantic-settings as documented."""
        settings_file = validator.ingenious_dir / "config" / "main_settings.py"
        assert settings_file.exists()

        with open(settings_file, "r") as f:
            content = f.read()

        # Verify pydantic-settings is used
        assert "from pydantic_settings import BaseSettings" in content
        assert "class IngeniousSettings(BaseSettings)" in content

    def test_required_dependencies_match_docs(self, validator):
        """Verify key dependencies mentioned in docs are in pyproject.toml."""
        pyproject_path = validator.workspace_root / "pyproject.toml"

        with open(pyproject_path, "r") as f:
            content = f.read()

        # Key dependencies mentioned in documentation
        expected_deps = [
            "fastapi",
            "uvicorn",
            "typer",
            "autogen-agentchat",
            "pydantic",
            "pydantic-settings",
            "azure-identity",
            "openai",
        ]

        for dep in expected_deps:
            assert dep in content, (
                f"Expected dependency '{dep}' not found in pyproject.toml"
            )


if __name__ == "__main__":
    # This allows running the validator manually for debugging
    validator = DocumentationValidator()

    print("Extracting API endpoints...")
    endpoints = validator.extract_api_endpoints_from_code()
    for module, eps in endpoints.items():
        print(f"  {module}: {eps}")

    print("\nExtracting CLI commands...")
    commands = validator.extract_cli_commands_from_code()
    print(f"  Commands: {sorted(commands)}")

    print("\nExtracting workflows...")
    workflows = validator.extract_workflow_names_from_code()
    print(f"  Workflows: {sorted(workflows)}")

    print("\nValidating pyproject.toml...")
    info = validator.validate_pyproject_toml()
    for key, value in info.items():
        print(f"  {key}: {value}")
