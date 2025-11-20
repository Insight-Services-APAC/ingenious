"""Validate CLI command for Insight Ingenious.

This module contains the validate command for comprehensive system validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.panel import Panel

from ingenious.cli.base import BaseCommand, CommandError, ExitCode
from ingenious.cli.utilities import ValidationUtils
from ingenious.common.enums import AuthenticationMethod


class ValidateCommand(BaseCommand):
    """Validate system configuration and requirements."""

    def execute(self, **kwargs: Any) -> None:
        """Comprehensive validation of Insight Ingenious setup.

        Performs deep validation of:
        • Environment variables and configuration
        • Configuration file syntax and required fields
        • Azure OpenAI connectivity
        • Dependencies and imports
        • Workflow requirements and availability
        """
        self.console.print("[bold blue]✅ Insight Ingenious Configuration Validation[/bold blue]\n")

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

    def _validate_environment_variables(self) -> tuple[bool, list[str]]:
        """Validate environment variables for pydantic-settings configuration."""
        issues: list[str] = []
        try:
            # Check for .env file
            from pathlib import Path

            from ingenious.config.settings import IngeniousSettings

            # Look for .env files
            env_files = [".env", ".env.local", ".env.dev", ".env.prod"]
            env_file_found = any(Path(f).exists() for f in env_files)

            if env_file_found:
                self.print_success("Environment file (.env) found")
            else:
                self.print_warning("No .env file found - using system environment variables")

            # Load settings and check if models are configured
            try:
                settings = IngeniousSettings()

                if settings.models and len(settings.models) > 0:
                    self.print_success("Configuration loaded successfully from environment")

                    # Check if first model has required fields based on authentication method
                    first_model = settings.models[0]

                    # Check required fields based on authentication method
                    auth_method = first_model.authentication_method

                    # Base fields required for all authentication methods
                    required_fields_check = bool(first_model.base_url and first_model.model)

                    # Additional validation based on authentication method
                    auth_validation_passed = True
                    auth_validation_message = ""

                    if auth_method == AuthenticationMethod.DEFAULT_CREDENTIAL:
                        # No additional fields required for default credential
                        auth_validation_message = (
                            "default_credential authentication (no additional credentials required)"
                        )
                    elif auth_method == AuthenticationMethod.MSI:
                        # MSI requires client_id
                        if not first_model.client_id:
                            auth_validation_passed = False
                        else:
                            auth_validation_message = "MSI authentication with client_id"
                    elif auth_method == AuthenticationMethod.TOKEN:
                        # TOKEN requires api_key
                        if not first_model.api_key:
                            auth_validation_passed = False
                        else:
                            auth_validation_message = "token authentication with API key"
                    elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
                        # CLIENT_ID_AND_SECRET requires both client_id and client_secret
                        if not first_model.client_id or not first_model.client_secret:
                            auth_validation_passed = False
                        else:
                            auth_validation_message = "client_id_and_secret authentication"

                    # Overall validation check
                    required_fields_check = required_fields_check and auth_validation_passed

                    if required_fields_check:
                        self.print_success("Primary model environment configuration is complete")
                        self.console.print(f"    📋 Using {auth_validation_message}")
                        return True, issues
                    else:
                        missing_fields = []
                        if not first_model.base_url:
                            missing_fields.append("base_url")
                        if not first_model.model:
                            missing_fields.append("model")

                        # Check authentication-specific required fields
                        if auth_method == AuthenticationMethod.MSI and not first_model.client_id:
                            missing_fields.append("client_id (required for MSI authentication)")
                        elif auth_method == AuthenticationMethod.TOKEN and not first_model.api_key:
                            missing_fields.append("api_key (required for TOKEN authentication)")
                        elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
                            if not first_model.client_id:
                                missing_fields.append(
                                    "client_id (required for CLIENT_ID_AND_SECRET authentication)"
                                )
                            if not first_model.client_secret:
                                missing_fields.append(
                                    "client_secret (required for CLIENT_ID_AND_SECRET authentication)"
                                )
                            # Check tenant_id - allow empty if AZURE_TENANT_ID env var exists
                            if not first_model.tenant_id:
                                import os

                                if not os.getenv("AZURE_TENANT_ID"):
                                    missing_fields.append(
                                        "tenant_id (required for CLIENT_ID_AND_SECRET authentication, can use AZURE_TENANT_ID env var)"
                                    )

                        self.print_error(
                            f"Model missing required configuration: {', '.join(missing_fields)}"
                        )
                        issues.append(f"Missing model configuration: {', '.join(missing_fields)}")
                        self._show_env_fix_commands()
                        return False, issues
                else:
                    self.print_error("No models configured in environment")
                    issues.append("No models configured")
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

    def _validate_configuration_files(self) -> tuple[bool, list[str]]:
        """Validate pydantic-settings configuration."""
        success = True
        issues = []

        try:
            # Import and validate pydantic-settings configuration
            from ingenious.config.settings import IngeniousSettings

            # Attempt to load and validate the configuration
            settings = IngeniousSettings()

            # Call the validation method if it exists
            if hasattr(settings, "validate_configuration"):
                settings.validate_configuration()

            self.print_success("Pydantic-settings configuration validation passed")

            # Validate that required models are configured
            if settings.models and len(settings.models) > 0:
                self.print_success(f"Found {len(settings.models)} configured model(s)")

                # Validate first model has required fields based on authentication method
                first_model = settings.models[0]
                auth_method = first_model.authentication_method

                # Base fields required for all authentication methods
                required_fields_check = bool(first_model.base_url and first_model.model)

                # Additional validation based on authentication method
                auth_validation_passed = True

                if auth_method == AuthenticationMethod.DEFAULT_CREDENTIAL:
                    # No additional fields required for default credential
                    pass
                elif auth_method == AuthenticationMethod.MSI:
                    # MSI requires client_id
                    if not first_model.client_id:
                        auth_validation_passed = False
                elif auth_method == AuthenticationMethod.TOKEN:
                    # TOKEN requires api_key
                    if not first_model.api_key:
                        auth_validation_passed = False
                elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
                    # CLIENT_ID_AND_SECRET requires both client_id and client_secret
                    if not first_model.client_id or not first_model.client_secret:
                        auth_validation_passed = False

                # Overall validation check
                required_fields_check = required_fields_check and auth_validation_passed

                if required_fields_check:
                    self.print_success("Primary model configuration is complete")
                    self.console.print(f"    📋 Using {auth_method.value} authentication")
                else:
                    missing_fields = []
                    if not first_model.base_url:
                        missing_fields.append("base_url")
                    if not first_model.model:
                        missing_fields.append("model")

                    # Check authentication-specific required fields
                    if auth_method == AuthenticationMethod.MSI and not first_model.client_id:
                        missing_fields.append("client_id (required for MSI authentication)")
                    elif auth_method == AuthenticationMethod.TOKEN and not first_model.api_key:
                        missing_fields.append("api_key (required for TOKEN authentication)")
                    elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
                        if not first_model.client_id:
                            missing_fields.append(
                                "client_id (required for CLIENT_ID_AND_SECRET authentication)"
                            )
                        if not first_model.client_secret:
                            missing_fields.append(
                                "client_secret (required for CLIENT_ID_AND_SECRET authentication)"
                            )
                        # Check tenant_id - allow empty if AZURE_TENANT_ID env var exists
                        if not first_model.tenant_id:
                            import os

                            if not os.getenv("AZURE_TENANT_ID"):
                                missing_fields.append(
                                    "tenant_id (required for CLIENT_ID_AND_SECRET authentication, can use AZURE_TENANT_ID env var)"
                                )

                    self.print_error(
                        f"Primary model missing required fields: {', '.join(missing_fields)}"
                    )
                    issues.append(
                        f"Model configuration incomplete: missing {', '.join(missing_fields)}"
                    )
                    success = False
            else:
                self.print_error("No models configured in settings")
                issues.append("No models configured")
                success = False

        except Exception as e:
            self.print_error(f"Configuration validation failed: {e}")
            issues.append(f"Configuration: {e}")
            success = False

        return success, issues

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
            self.console.print("    Install with: uv add ingenious[azure,full] for all features")

        if success:
            self.print_success("Core dependencies available")

        return success, issues

    def _validate_azure_connectivity(self) -> tuple[bool, list[str]]:
        """Validate Azure OpenAI connectivity using pydantic-settings."""
        issues = []

        try:
            from ingenious.config.settings import IngeniousSettings

            # Load settings and check for configured models
            settings = IngeniousSettings()

            if not settings.models or len(settings.models) == 0:
                self.print_error("No models configured")
                issues.append("No Azure OpenAI models configured")
                return False, issues

            # Check first model configuration based on authentication method
            first_model = settings.models[0]
            auth_method = first_model.authentication_method

            # Validate credentials based on authentication method
            auth_validation_passed = True

            if auth_method == AuthenticationMethod.DEFAULT_CREDENTIAL:
                # No additional credentials required
                self.print_success("Using default_credential authentication (no API key required)")
            elif auth_method == AuthenticationMethod.MSI:
                if not first_model.client_id:
                    self.print_error(
                        "MSI authentication requires client_id but it's not configured"
                    )
                    issues.append("MSI authentication client_id not configured")
                    auth_validation_passed = False
                else:
                    self.print_success(
                        f"Using MSI authentication with client_id: {first_model.client_id}"
                    )
            elif auth_method == AuthenticationMethod.TOKEN:
                if not first_model.api_key:
                    self.print_error(
                        "TOKEN authentication requires api_key but it's not configured"
                    )
                    issues.append("TOKEN authentication API key not configured")
                    auth_validation_passed = False
                else:
                    self.print_success("Using TOKEN authentication with API key")
            elif auth_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
                missing_creds = []
                if not first_model.client_id:
                    missing_creds.append("client_id")
                if not first_model.client_secret:
                    missing_creds.append("client_secret")
                # Check tenant_id - allow empty if AZURE_TENANT_ID env var exists
                if not first_model.tenant_id:
                    import os

                    if not os.getenv("AZURE_TENANT_ID"):
                        missing_creds.append("tenant_id (or AZURE_TENANT_ID env var)")

                if missing_creds:
                    self.print_error(
                        f"CLIENT_ID_AND_SECRET authentication requires {', '.join(missing_creds)} but they're not configured"
                    )
                    issues.append(
                        f"CLIENT_ID_AND_SECRET authentication missing: {', '.join(missing_creds)}"
                    )
                    auth_validation_passed = False
                else:
                    self.print_success("Using CLIENT_ID_AND_SECRET authentication")

            if not auth_validation_passed:
                return False, issues

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

            # Test actual connectivity to Azure OpenAI service
            try:
                import urllib.parse

                import requests

                # Create a test URL to check connectivity
                parsed_url = urllib.parse.urlparse(first_model.base_url)
                test_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

                # Simple connectivity test with timeout
                response = requests.get(test_url, timeout=10)
                if response.status_code in [
                    200,
                    401,
                    403,
                    404,
                ]:  # Service is responding
                    self.print_success("Azure OpenAI service is reachable")
                else:
                    self.print_warning(
                        f"Azure OpenAI service returned status {response.status_code}"
                    )
                    issues.append(
                        f"Azure service returned unexpected status: {response.status_code}"
                    )

            except ImportError:
                self.print_info("Skipping connectivity test - requests library not available")
            except Exception as conn_e:
                # Handle all other connectivity errors (timeout, connection error, etc.)
                if "ConnectTimeout" in str(type(conn_e)):
                    self.print_warning(
                        "Azure OpenAI service connection timeout - check network connectivity"
                    )
                    issues.append("Azure OpenAI service connection timeout")
                elif "ConnectionError" in str(type(conn_e)):
                    self.print_warning(
                        "Cannot connect to Azure OpenAI service - check endpoint URL and network"
                    )
                    issues.append("Cannot connect to Azure OpenAI service")
                else:
                    self.print_warning(f"Azure connectivity test failed: {conn_e}")
                # Don't treat connectivity test failures as critical errors

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
                                issues.append(f"{workflow.replace('_', '-')} workflow not found")
                            workflows_checked += 1
                        except ImportError as e:
                            self.console.print(
                                f"    ❌ {workflow.replace('_', '-')}: Import failed"
                            )
                            workflows_checked += 1
                            issues.append(f"{workflow.replace('_', '-')} import failed: {e}")

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
                    issues.append(f"Port {port} is already in use - server may fail to start")

                    # Try to identify what's using the port
                    try:
                        import subprocess  # nosec B404

                        if hasattr(subprocess, "run"):
                            # Try lsof command on Unix-like systems
                            proc_result = subprocess.run(  # nosec B603 B607
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
            "INGENIOUS_MODELS__0__MODEL=gpt-5-mini",
            "INGENIOUS_MODELS__0__API_VERSION=2024-02-01",
            "INGENIOUS_MODELS__0__DEPLOYMENT=gpt-5-mini",
        ]

        panel = Panel(
            "\n".join(fix_commands),
            title="🔧 Environment Configuration Setup",
            border_style="yellow",
        )
        self.console.print(panel)

    def _show_validation_summary(self, validation_passed: bool, issues_found: list[str]) -> None:
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
                        "  export INGENIOUS_PROJECT_PATH=$(pwd)/config.yml",
                        "  export INGENIOUS_PROFILE_PATH=$(pwd)/profiles.yml",
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
