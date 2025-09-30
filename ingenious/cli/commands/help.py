"""
Help and status CLI commands for Insight Ingenious.

This module contains commands for getting help, checking status, and validating configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from rich.panel import Panel

from ingenious.cli.base import BaseCommand, CommandError, ExitCode
from ingenious.cli.utilities import OutputFormatters, ValidationUtils
from ingenious.common.enums import AuthenticationMethod
from ingenious.config.models import ModelSettings


class HelpCommand(BaseCommand):
    """Show detailed help and getting started guide."""

    def execute(self, topic: Optional[str] = None, **kwargs: Any) -> None:
        """
        Show comprehensive help for getting started with Insight Ingenious.

        Args:
            topic: Specific topic to show help for (setup, workflows, config, deployment)
        """
        if topic is None:
            self._show_general_help()
        elif topic == "setup":
            self._show_setup_help()
        elif topic == "workflows":
            self._show_workflows_help()
        elif topic == "config":
            self._show_config_help()
        elif topic == "deployment":
            self._show_deployment_help()
        else:
            self.print_error(f"Unknown help topic: {topic}")
            self.console.print(
                "\nAvailable topics: setup, workflows, config, deployment"
            )
            self.console.print("Use 'ingen help' for general help.")
            raise CommandError(
                f"Invalid help topic: {topic}", ExitCode.VALIDATION_ERROR
            )

    def _show_general_help(self) -> None:
        """Show general help information."""
        self.console.print(
            "[bold blue]🚀 Insight Ingenious - Quick Start Guide[/bold blue]\n"
        )

        sections = [
            ("1. Initialize a new project:", "ingen init"),
            (
                "2. Configure your project:",
                "• Copy .env.example to .env and add your API keys\n   • Set INGENIOUS_MODELS__0__* entries for your model",
            ),
            (
                "3. Set environment variables:",
                "export INGENIOUS_MODELS__0__API_KEY=your-key\n   export INGENIOUS_MODELS__0__BASE_URL=https://your-endpoint",
            ),
            ("4. Start the server:", "ingen serve"),
            (
                "5. Access the interfaces:",
                "• API: http://localhost:80\n   • Chat: http://localhost:80/chainlit\n   • Prompt Tuner: http://localhost:80/prompt-tuner",
            ),
        ]

        for title, content in sections:
            self.console.print(f"[bold]{title}[/bold]")
            self.console.print(f"   {content}")
            self.console.print("")

        helpful_commands = Panel(
            "ingen status      # Check configuration\n"
            "ingen workflows   # List available workflows\n"
            "ingen test        # Run tests\n"
            "ingen help <topic> # Get detailed help on specific topics",
            title="💡 Helpful Commands",
            border_style="yellow",
        )
        self.console.print(helpful_commands)

        docs_panel = Panel(
            "GitHub: https://github.com/Insight-Services-APAC/ingenious",
            title="📖 Documentation",
            border_style="blue",
        )
        self.console.print(docs_panel)

    def _show_setup_help(self) -> None:
        """Show setup-specific help."""
        content = (
            "To set up your Insight Ingenious project:\n\n"
            "1. Run `ingen init` to generate project files\n"
            "2. Configure API keys and settings in `.env`\n"
            "3. Set INGENIOUS_MODELS__0__* environment variables for your model\n"
            "4. Optionally provide a custom .env file with `ingen serve --env-file`\n"
            "5. Start the server with `ingen serve`"
        )

        panel = Panel(content, title="🛠️  Project Setup Guide", border_style="blue")
        self.console.print(panel)

    def _show_workflows_help(self) -> None:
        """Show workflows-specific help."""
        content = (
            "Workflows are the core of Insight Ingenious. They define how agents\n"
            "process and respond to user inputs.\n\n"
            "Use 'ingen workflows' to see all available workflows and their requirements."
        )

        panel = Panel(content, title="🔄 Workflows Guide", border_style="blue")
        self.console.print(panel)

    def _show_config_help(self) -> None:
        """Show configuration-specific help."""
        content = (
            "Configuration is managed through environment variables:\n"
            "• .env / .env.local - Primary configuration sources\n"
            "• INGENIOUS_MODELS__* - Model and service settings"
        )

        panel = Panel(content, title="⚙️  Configuration Guide", border_style="blue")
        self.console.print(panel)

    def _show_deployment_help(self) -> None:
        """Show deployment-specific help."""
        content = (
            "Insight Ingenious can be deployed in several ways:\n"
            "• Local development: ingen serve\n"
            "• Docker: Use provided Docker templates\n"
            "• Cloud: Deploy to Azure, AWS, or other cloud providers"
        )

        panel = Panel(content, title="🚀 Deployment Guide", border_style="blue")
        self.console.print(panel)


class StatusCommand(BaseCommand):
    """Check system status and configuration."""

    def execute(self, **kwargs: Any) -> None:
        """
        Check the status of Insight Ingenious configuration.

        Validates:
        • Configuration files existence and validity
        • Environment variables
        • Required dependencies
        • Available workflows
        """
        self.console.print(
            "[bold blue]🔍 Insight Ingenious System Status[/bold blue]\n"
        )

        status_items: dict[str, Any] = {}

        # Check environment variables
        self._check_environment_variables(status_items)

        # Check local files
        self._check_local_files(status_items)

        # Display status table
        table = OutputFormatters.create_status_table(status_items, "System Status")
        self.console.print(table)

        # Show recommendations if needed
        self._show_recommendations(status_items)

    def _check_environment_variables(self, status_items: dict[str, object]) -> None:
        """Check environment variables status."""
        required_env_sets = {
            "Model API key": [
                "INGENIOUS_MODELS__0__API_KEY",
                "AZURE_OPENAI_API_KEY",
            ],
            "Model base URL": [
                "INGENIOUS_MODELS__0__BASE_URL",
                "AZURE_OPENAI_BASE_URL",
            ],
            "Model name": [
                "INGENIOUS_MODELS__0__MODEL",
                "AZURE_OPENAI_MODEL",
            ],
        }

        for label, candidates in required_env_sets.items():
            value = next((os.getenv(var) for var in candidates if os.getenv(var)), None)
            if value:
                status_items[label] = {
                    "status": "OK",
                    "details": f"Provided via {next(var for var in candidates if os.getenv(var))}",
                }
            else:
                status_items[label] = {
                    "status": "Missing",
                    "details": f"Set one of: {', '.join(candidates)}",
                }

    def _check_local_files(self, status_items: dict[str, object]) -> None:
        """Check local configuration files."""
        files_to_check = {
            ".env": Path.cwd() / ".env",
            ".env.example": Path.cwd() / ".env.example",
        }

        for name, path in files_to_check.items():
            if path.exists():
                status_items[f"Local {name}"] = {"status": "OK", "details": str(path)}
            else:
                status_items[f"Local {name}"] = {
                    "status": "Missing",
                    "details": "File not found in current directory",
                }

    def _show_recommendations(self, status_items: dict[str, object]) -> None:
        """Show setup recommendations based on status."""
        has_issues = any(
            item.get("status", "").lower() in ["missing", "warning", "error"]
            for item in status_items.values()
            if isinstance(item, dict)
        )

        if has_issues:
            recommendations = [
                "cp .env.example .env  # Create local environment file",
                "export INGENIOUS_MODELS__0__API_KEY=your-key",
                "export INGENIOUS_MODELS__0__BASE_URL=https://your-endpoint",
            ]

            if any("Missing" in str(item) for item in status_items.values()):
                recommendations.insert(0, "ingen init  # Initialize missing files")

            panel = Panel(
                "\n".join(recommendations),
                title="💡 Quick Setup Recommendations",
                border_style="yellow",
            )
            self.console.print("\n")
            self.console.print(panel)


class VersionCommand(BaseCommand):
    """Show version information."""

    def execute(self, **kwargs: Any) -> None:
        """Display version information for Insight Ingenious."""
        try:
            from importlib.metadata import version as get_version

            version_str = get_version("insight-ingenious")
            self.console.print(
                f"[bold blue]Insight Ingenious[/bold blue] version [bold]{version_str}[/bold]"
            )
        except Exception:
            self.console.print(
                "[bold blue]Insight Ingenious[/bold blue] - Development Version"
            )

        self.console.print("🚀 GenAI Accelerator Framework")
        self.console.print(
            "📖 Documentation: https://github.com/Insight-Services-APAC/ingenious"
        )


class ValidateCommand(BaseCommand):
    """Validate system configuration and requirements."""

    def execute(self, **kwargs: Any) -> None:
        """
        Comprehensive validation of Insight Ingenious setup.

        Performs deep validation of:
        • Environment variables and configuration
        • Configuration file syntax and required fields
        • Azure OpenAI connectivity
        • Dependencies and imports
        • Workflow requirements and availability
        """
        self.console.print(
            "[bold blue]✅ Insight Ingenious Configuration Validation[/bold blue]\n"
        )

        validation_passed = True
        issues_found = []

        # 1. Check environment variables
        self.print_info("1. Checking environment variables...")
        env_passed, env_issues = self._validate_environment_variables()
        validation_passed = validation_passed and env_passed
        issues_found.extend(env_issues)

        # 2. Validate configuration files
        self.print_info("2. Validating configuration files...")
        config_passed, config_issues = self._validate_configuration_files()
        validation_passed = validation_passed and config_passed
        issues_found.extend(config_issues)

        # 3. Check dependencies
        self.print_info("3. Checking dependencies...")
        deps_passed, deps_issues = self._validate_dependencies()
        validation_passed = validation_passed and deps_passed
        issues_found.extend(deps_issues)

        # 4. Check Azure OpenAI connectivity
        self.print_info("4. Checking Azure OpenAI connectivity...")
        azure_passed, azure_issues = self._validate_azure_connectivity()
        validation_passed = validation_passed and azure_passed
        issues_found.extend(azure_issues)

        # 5. Check port availability
        self.print_info("5. Checking port availability...")
        port_passed, port_issues = self._validate_port_availability()
        validation_passed = validation_passed and port_passed
        issues_found.extend(port_issues)

        # 6. Check workflow availability
        self.print_info("6. Checking workflow availability...")
        workflow_passed, workflow_issues = self._validate_workflows()
        validation_passed = validation_passed and workflow_passed
        issues_found.extend(workflow_issues)

        # 7. Summary and recommendations
        self._show_validation_summary(validation_passed, issues_found)

        if not validation_passed:
            raise CommandError("Validation failed", ExitCode.VALIDATION_ERROR)

    def _check_env_files(self) -> bool:
        """Check for existence of environment files."""
        from pathlib import Path

        env_files = [".env", ".env.local", ".env.dev", ".env.prod"]
        env_file_found = any(Path(f).exists() for f in env_files)

        if env_file_found:
            self.print_success("Environment file (.env) found")
        else:
            self.print_warning(
                "No .env file found - using system environment variables"
            )
        return env_file_found

    def _validate_auth_method(
        self, first_model: ModelSettings, auth_method: AuthenticationMethod
    ) -> tuple[bool, str]:
        """Validate authentication method specific requirements."""
        auth_validators = {
            AuthenticationMethod.DEFAULT_CREDENTIAL: self._validate_default_credential,
            AuthenticationMethod.MSI: self._validate_msi,
            AuthenticationMethod.TOKEN: self._validate_token,
            AuthenticationMethod.CLIENT_ID_AND_SECRET: self._validate_client_secret,
        }

        validator = auth_validators.get(auth_method, self._validate_default_credential)
        return validator(first_model)

    def _validate_default_credential(self, model: ModelSettings) -> tuple[bool, str]:
        """Validate default credential authentication."""
        return (
            True,
            "default_credential authentication (no additional credentials required)",
        )

    def _validate_msi(self, model: ModelSettings) -> tuple[bool, str]:
        """Validate MSI authentication."""
        if not model.client_id:
            return False, ""
        return True, "MSI authentication with client_id"

    def _validate_token(self, model: ModelSettings) -> tuple[bool, str]:
        """Validate token authentication."""
        if not model.api_key:
            return False, ""
        return True, "token authentication with API key"

    def _validate_client_secret(self, model: ModelSettings) -> tuple[bool, str]:
        """Validate client ID and secret authentication."""
        if not model.client_id or not model.client_secret:
            return False, ""
        return True, "client_id_and_secret authentication"

    def _get_base_missing_fields(self, model: ModelSettings) -> list[str]:
        """Get missing base fields."""
        missing = []
        if not model.base_url:
            missing.append("base_url")
        if not model.model:
            missing.append("model")
        return missing

    def _get_auth_missing_fields(
        self, model: ModelSettings, auth_method: AuthenticationMethod
    ) -> list[str]:
        """Get missing authentication-specific fields."""
        auth_field_checkers = {
            AuthenticationMethod.MSI: self._check_msi_fields,
            AuthenticationMethod.TOKEN: self._check_token_fields,
            AuthenticationMethod.CLIENT_ID_AND_SECRET: self._check_client_secret_fields,
        }

        checker = auth_field_checkers.get(auth_method)
        if checker:
            return checker(model)
        return []

    def _check_msi_fields(self, model: ModelSettings) -> list[str]:
        """Check MSI authentication fields."""
        if not model.client_id:
            return ["client_id (required for MSI authentication)"]
        return []

    def _check_token_fields(self, model: ModelSettings) -> list[str]:
        """Check token authentication fields."""
        if not model.api_key:
            return ["api_key (required for TOKEN authentication)"]
        return []

    def _check_client_secret_fields(self, model: ModelSettings) -> list[str]:
        """Check client secret authentication fields."""
        missing = []
        if not model.client_id:
            missing.append(
                "client_id (required for CLIENT_ID_AND_SECRET authentication)"
            )
        if not model.client_secret:
            missing.append(
                "client_secret (required for CLIENT_ID_AND_SECRET authentication)"
            )
        if not model.tenant_id and not os.getenv("AZURE_TENANT_ID"):
            missing.append(
                "tenant_id (required for CLIENT_ID_AND_SECRET authentication, can use AZURE_TENANT_ID env var)"
            )
        return missing

    def _get_missing_fields(
        self, first_model: ModelSettings, auth_method: AuthenticationMethod
    ) -> list[str]:
        """Get list of missing required fields based on auth method."""
        missing_fields = self._get_base_missing_fields(first_model)
        missing_fields.extend(self._get_auth_missing_fields(first_model, auth_method))
        return missing_fields

    def _validate_environment_variables(self) -> tuple[bool, list[str]]:
        """Validate environment variables for pydantic-settings configuration."""
        issues: list[str] = []

        try:
            from ingenious.config.main_settings import IngeniousSettings

            # Check for environment files
            self._check_env_files()

            # Load and validate settings
            try:
                settings = IngeniousSettings()

                if not settings.models or len(settings.models) == 0:
                    self.print_error("No models configured in environment")
                    issues.append("No models configured")
                    self._show_env_fix_commands()
                    return False, issues

                self.print_success("Configuration loaded successfully from environment")

                # Validate first model
                first_model = settings.models[0]
                auth_method = first_model.authentication_method

                # Check base requirements
                base_valid = bool(first_model.base_url and first_model.model)

                # Check auth-specific requirements
                auth_valid, auth_message = self._validate_auth_method(
                    first_model, auth_method
                )

                if base_valid and auth_valid:
                    self.print_success(
                        "Primary model environment configuration is complete"
                    )
                    self.console.print(f"    📋 Using {auth_message}")
                    return True, issues

                # Handle missing fields
                missing_fields = self._get_missing_fields(first_model, auth_method)
                self.print_error(
                    f"Model missing required configuration: {', '.join(missing_fields)}"
                )
                issues.append(
                    f"Missing model configuration: {', '.join(missing_fields)}"
                )
                self._show_env_fix_commands()
                return False, issues

            except Exception as e:
                self.print_error(f"Failed to load configuration: {e}")
                issues.append(f"Configuration loading error: {e}")
                self._show_env_fix_commands()
                return False, issues

        except Exception as e:
            self.print_error(f"Environment validation failed: {e}")
            issues.append(f"Environment setup: {e}")
            return False, issues

    def _validate_model_config(self, model: ModelSettings) -> tuple[bool, list[str]]:
        """Validate a single model configuration."""
        auth_method = model.authentication_method

        # Check base requirements
        base_valid = bool(model.base_url and model.model)

        # Check auth-specific requirements
        auth_valid, auth_message = self._validate_auth_method(model, auth_method)

        if base_valid and auth_valid:
            return True, []

        # Get missing fields
        missing_fields = self._get_missing_fields(model, auth_method)
        return False, missing_fields

    def _validate_configuration_files(self) -> tuple[bool, list[str]]:
        """Validate pydantic-settings configuration."""
        issues = []

        try:
            from ingenious.config.main_settings import IngeniousSettings

            # Load and validate configuration
            settings = IngeniousSettings()

            # Call validation if exists
            if hasattr(settings, "validate_configuration"):
                settings.validate_configuration()

            self.print_success("Pydantic-settings configuration validation passed")

            # Check models
            if not settings.models or len(settings.models) == 0:
                self.print_error("No models configured in settings")
                issues.append("No models configured")
                return False, issues

            self.print_success(f"Found {len(settings.models)} configured model(s)")

            # Validate first model
            first_model = settings.models[0]
            valid, missing_fields = self._validate_model_config(first_model)

            if valid:
                auth_method = first_model.authentication_method
                self.print_success("Primary model configuration is complete")
                self.console.print(f"    📋 Using {auth_method.value} authentication")
                return True, issues

            # Handle validation failure
            self.print_error(
                f"Primary model missing required fields: {', '.join(missing_fields)}"
            )
            issues.append(
                f"Model configuration incomplete: missing {', '.join(missing_fields)}"
            )
            return False, issues

        except Exception as e:
            self.print_error(f"Configuration validation failed: {e}")
            issues.append(f"Configuration: {e}")
            return False, issues

    def _validate_dependencies(self) -> tuple[bool, list[str]]:
        """Validate required dependencies are available."""
        success = True
        issues = []

        # Core dependencies that should always be available
        core_deps = [
            ("pandas", "Required for sql-manipulation-agent"),
            ("fastapi", "Core web framework"),
            ("openai", "Azure OpenAI connectivity"),
            ("typer", "CLI framework"),
        ]

        optional_deps = [
            ("chromadb", "Required for knowledge-base-agent"),
            ("azure.storage.blob", "Required for Azure Blob Storage"),
            ("pyodbc", "Required for SQL database connectivity"),
        ]

        # Check core dependencies
        for dep_name, description in core_deps:
            try:
                __import__(dep_name)
                self.console.print(f"    ✅ {dep_name}: Available")
            except ImportError:
                self.print_error(f"Missing dependency: {dep_name} ({description})")
                issues.append(f"Missing core dependency: {dep_name}")
                success = False

        # Check optional dependencies (warn but don't fail)
        missing_optional = []
        for dep_name, description in optional_deps:
            try:
                __import__(dep_name)
                self.console.print(f"    ✅ {dep_name}: Available")
            except ImportError:
                self.console.print(f"    ⚠️  {dep_name}: Not available ({description})")
                missing_optional.append(dep_name)

        if missing_optional:
            self.console.print(
                f"    💡 Optional dependencies missing: {', '.join(missing_optional)}"
            )
            self.console.print(
                "    Install with: uv add ingenious[azure,full] for all features"
            )

        if success:
            self.print_success("Core dependencies available")

        return success, issues

    def _validate_auth_credentials(
        self, model: ModelSettings
    ) -> tuple[bool, list[str]]:
        """Validate authentication credentials for connectivity."""
        issues = []
        auth_method = model.authentication_method
        auth_valid, auth_message = self._validate_auth_method(model, auth_method)

        if auth_valid:
            self.print_success(auth_message)
        else:
            missing_fields = self._get_auth_missing_fields(model, auth_method)
            for field in missing_fields:
                issues.append(f"{auth_method.value} authentication: {field}")
            self.print_error(f"{auth_method.value} authentication incomplete")

        return auth_valid, issues

    def _test_azure_connection(self, base_url: str) -> tuple[bool, str]:
        """Test actual connectivity to Azure OpenAI service."""
        try:
            import urllib.parse

            import requests

            # Create a test URL to check connectivity
            parsed_url = urllib.parse.urlparse(base_url)
            test_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # Simple connectivity test with timeout
            response = requests.get(test_url, timeout=10)
            if response.status_code in [200, 401, 403, 404]:
                self.print_success("Azure OpenAI service is reachable")
                return True, ""

            self.print_warning(
                f"Azure OpenAI service returned status {response.status_code}"
            )
            return (
                True,
                f"Azure service returned unexpected status: {response.status_code}",
            )

        except ImportError:
            self.print_info(
                "Skipping connectivity test - requests library not available"
            )
            return True, ""
        except Exception as conn_e:
            error_type = str(type(conn_e))
            if "ConnectTimeout" in error_type:
                self.print_warning(
                    "Azure OpenAI service connection timeout - check network connectivity"
                )
                return True, "Azure OpenAI service connection timeout"
            elif "ConnectionError" in error_type:
                self.print_warning(
                    "Cannot connect to Azure OpenAI service - check endpoint URL and network"
                )
                return True, "Cannot connect to Azure OpenAI service"
            else:
                self.print_warning(f"Azure connectivity test failed: {conn_e}")
                return True, f"Azure connectivity test failed: {conn_e}"

    def _validate_azure_connectivity(self) -> tuple[bool, list[str]]:
        """Validate Azure OpenAI connectivity using pydantic-settings."""
        issues = []

        try:
            from ingenious.config.main_settings import IngeniousSettings

            # Load settings
            settings = IngeniousSettings()

            if not settings.models or len(settings.models) == 0:
                self.print_error("No models configured")
                issues.append("No Azure OpenAI models configured")
                return False, issues

            # Validate first model
            first_model = settings.models[0]

            # Validate credentials
            auth_valid, auth_issues = self._validate_auth_credentials(first_model)
            issues.extend(auth_issues)

            if not auth_valid:
                return False, issues

            # Check base URL
            if not first_model.base_url:
                self.print_error("Azure OpenAI endpoint not configured")
                issues.append("Azure OpenAI endpoint not configured")
                return False, issues

            # Validate URL format
            is_valid_url, error = ValidationUtils.validate_url(first_model.base_url)
            if not is_valid_url:
                self.print_error(f"Invalid Azure endpoint URL: {error}")
                issues.append(f"Invalid Azure endpoint URL: {error}")
                return False, issues

            # Test connectivity
            _, conn_issue = self._test_azure_connection(first_model.base_url)
            if conn_issue:
                issues.append(conn_issue)

            self.print_success("Azure OpenAI configuration found")
            return True, issues

        except Exception as e:
            self.print_error(f"Azure connectivity validation failed: {e}")
            issues.append(f"Azure connectivity: {e}")
            return False, issues

    def _validate_workflows(self) -> tuple[bool, list[str]]:
        """Validate workflow availability."""
        issues = []
        try:
            extensions_path = Path.cwd() / "ingenious_extensions"
            if extensions_path.exists():
                self.print_success("ingenious_extensions directory found")

                services_path = extensions_path / "services"
                if services_path.exists():
                    self.print_success("Services directory found")

                    # Try to validate specific workflows
                    workflows_checked = 0
                    workflows_working = 0

                    # Check bike-insights workflow (template workflow)
                    bike_insights_path = (
                        services_path
                        / "chat_services"
                        / "multi_agent"
                        / "conversation_flows"
                        / "bike_insights"
                    )
                    if bike_insights_path.exists():
                        self.console.print("    ✅ bike-insights: Available")
                        workflows_checked += 1
                        workflows_working += 1
                    else:
                        self.console.print("    ❌ bike-insights: Not found")
                        workflows_checked += 1
                        issues.append("bike-insights workflow not found")

                    # Check core workflows import
                    import importlib.util

                    core_workflows = [
                        "classification_agent",
                        "knowledge_base_agent",
                        "sql_manipulation_agent",
                    ]

                    for workflow in core_workflows:
                        try:
                            spec = importlib.util.find_spec(
                                f"ingenious.services.chat_services.multi_agent.conversation_flows.{workflow}"
                            )
                            if spec is not None:
                                self.console.print(
                                    f"    ✅ {workflow.replace('_', '-')}: Available"
                                )
                                workflows_working += 1
                            else:
                                self.console.print(
                                    f"    ❌ {workflow.replace('_', '-')}: Not found"
                                )
                                issues.append(
                                    f"{workflow.replace('_', '-')} workflow not found"
                                )
                            workflows_checked += 1
                        except ImportError as e:
                            self.console.print(
                                f"    ❌ {workflow.replace('_', '-')}: Import failed"
                            )
                            workflows_checked += 1
                            issues.append(
                                f"{workflow.replace('_', '-')} import failed: {e}"
                            )

                    self.console.print(
                        f"    📊 Workflows status: {workflows_working}/{workflows_checked} working"
                    )

                    return workflows_working > 0, issues
                else:
                    self.print_warning("Services directory not found")
                    issues.append("Services directory missing")
                    return False, issues
            else:
                self.print_error("ingenious_extensions directory not found")
                issues.append("ingenious_extensions directory missing")
                return False, issues
        except Exception as e:
            self.print_error(f"Workflow validation failed: {e}")
            issues.append(f"Workflow validation error: {e}")
            return False, issues

    def _validate_port_availability(self) -> tuple[bool, list[str]]:
        """Validate that configured ports are available for binding."""
        issues = []
        try:
            import socket

            from ingenious.config import config as config_module

            config = config_module.get_config()
            port = config.web_configuration.port

            # Test if port is already in use
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)  # 2 second timeout
                result = sock.connect_ex(("localhost", port))

                if result == 0:
                    # Port is in use
                    self.print_warning(f"Port {port} is already in use")
                    issues.append(
                        f"Port {port} is already in use - server may fail to start"
                    )

                    # Try to identify what's using the port
                    try:
                        import subprocess

                        if hasattr(subprocess, "run"):
                            # Try lsof command on Unix-like systems
                            proc_result = subprocess.run(
                                ["lsof", "-i", f":{port}"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if proc_result.stdout:
                                self.print_info(f"Process using port {port}:")
                                self.console.print(f"    {proc_result.stdout.strip()}")
                    except (FileNotFoundError, Exception):
                        pass  # lsof not available or failed

                    return False, issues
                else:
                    # Port is available
                    self.print_success(f"Port {port} is available for binding")
                    return True, issues

        except ImportError:
            self.print_warning("Socket module not available - cannot test port binding")
            issues.append("Cannot test port availability")
            return False, issues
        except Exception as e:
            self.print_error(f"Port validation failed: {e}")
            issues.append(f"Port validation error: {e}")
            return False, issues

    def _show_env_fix_commands(self) -> None:
        """Show commands to fix environment variable issues."""
        fix_commands = [
            "# Create .env file with required configuration:",
            "cp .env.example .env",
            "# Edit .env file and set required variables:",
            "INGENIOUS_MODELS__0__API_KEY=your-azure-openai-api-key",
            "INGENIOUS_MODELS__0__BASE_URL=https://your-resource.openai.azure.com/",
            "INGENIOUS_MODELS__0__MODEL=gpt-4o-mini",
            "INGENIOUS_MODELS__0__API_VERSION=2024-02-01",
            "INGENIOUS_MODELS__0__DEPLOYMENT=gpt-4o-mini",
        ]

        panel = Panel(
            "\n".join(fix_commands),
            title="🔧 Environment Configuration Setup",
            border_style="yellow",
        )
        self.console.print(panel)

    def _show_validation_summary(
        self, validation_passed: bool, issues_found: list[str]
    ) -> None:
        """Show validation summary and next steps."""
        if validation_passed:
            success_panel = Panel(
                "🎉 All validations passed! Your Ingenious setup is ready.\n"
                "🚀 You can now run: ingen serve",
                title="✅ Validation Summary",
                border_style="green",
            )
            self.console.print(success_panel)
        else:
            # Show specific issues found
            if issues_found:
                self.console.print("\n[bold red]Issues Found:[/bold red]")
                for issue in issues_found:
                    self.console.print(f"  ❌ {issue}")
                self.console.print("")

            # Show fix suggestions based on issues
            fix_commands = []

            if any("missing" in issue.lower() for issue in issues_found):
                fix_commands.extend(
                    [
                        "• Missing files: ingen init",
                        "• Set environment variables:",
                        "  export INGENIOUS_MODELS__0__API_KEY=your-key",
                        "  export INGENIOUS_MODELS__0__BASE_URL=https://your-endpoint",
                    ]
                )

            if any("azure" in issue.lower() for issue in issues_found):
                fix_commands.extend(
                    [
                        "• Create .env file with Azure OpenAI credentials:",
                        "  echo 'AZURE_OPENAI_API_KEY=your-key' > .env",
                        "  echo 'AZURE_OPENAI_BASE_URL=https://your-resource.openai.azure.com/' >> .env",
                    ]
                )

            if any("dependency" in issue.lower() for issue in issues_found):
                fix_commands.extend(
                    [
                        "• Install missing dependencies:",
                        "  uv add ingenious[standard]  # For SQL agent support",
                        "  uv add ingenious[azure-full]  # For full Azure integration",
                    ]
                )

            if any("workflow" in issue.lower() for issue in issues_found):
                fix_commands.extend(
                    [
                        "• Fix workflow issues:",
                        "  Check that ingenious_extensions directory exists",
                        "  Verify workflow files are properly configured",
                    ]
                )

            if not fix_commands:
                fix_commands = ["• Run 'ingen init' to set up missing components"]

            error_panel = Panel(
                "\n".join(fix_commands),
                title="❌ Validation Issues - Suggested Fixes",
                border_style="red",
            )
            self.console.print(error_panel)


# Command registration functions for backward compatibility
def register_commands(app: Any, console: Any) -> None:
    """Register help commands with the typer app."""

    import typer
    from typing_extensions import Annotated

    @app.command(name="help", help="Show detailed help and getting started guide")  # type: ignore[misc]
    def help_command(
        topic: Annotated[
            Optional[str],
            typer.Argument(help="Specific topic: setup, workflows, config, deployment"),
        ] = None,
    ) -> None:
        """Show comprehensive help for getting started with Insight Ingenious."""
        cmd = HelpCommand(console)
        cmd.run(topic=topic)

    @app.command(name="status", help="Check system status and configuration")  # type: ignore[misc]
    def status() -> None:
        """Check the status of your Insight Ingenious configuration."""
        cmd = StatusCommand(console)
        cmd.run()

    @app.command(name="version", help="Show version information")  # type: ignore[misc]
    def version() -> None:
        """Display version information for Insight Ingenious."""
        cmd = VersionCommand(console)
        cmd.run()

    @app.command(name="validate", help="Validate system configuration and requirements")  # type: ignore[misc]
    def validate() -> None:
        """Comprehensive validation of your Insight Ingenious setup."""
        cmd = ValidateCommand(console)
        cmd.run()
