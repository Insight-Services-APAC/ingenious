"""Tests for ValidateCommand in cli/commands/validate_command.py."""

import os
from unittest.mock import MagicMock, patch

import pytest

from ingenious.cli.commands.validate_command import ValidateCommand
from ingenious.common.enums import AuthenticationMethod
from ingenious.config.models import ModelSettings


class TestValidateCommand:
    """Test suite for ValidateCommand."""

    @pytest.fixture
    def validate_command(self, mock_console):
        """Create a ValidateCommand instance for testing."""
        from rich.console import Console

        return ValidateCommand(console=Console())

    @pytest.fixture
    def mock_console(self):
        """Mock console for testing output."""
        with patch("rich.console.Console") as mock:
            yield mock.return_value

    def test_validate_environment_variables_with_required_vars_set(
        self, validate_command, mock_console
    ):
        """Test environment variable validation when required vars are set."""
        with patch.dict(
            os.environ,
            {
                "INGENIOUS_MODELS__0__API_KEY": "test-key",
                "INGENIOUS_MODELS__0__BASE_URL": "https://test.openai.azure.com/",
                "INGENIOUS_MODELS__0__MODEL": "gpt-4",
                "INGENIOUS_MODELS__0__API_VERSION": "2024-02-01",
            },
        ):
            success, issues = validate_command._validate_environment_variables()
            assert success
            assert len(issues) >= 0

    def test_validate_environment_variables_missing_required_vars(
        self, validate_command, mock_console
    ):
        """Test environment variable validation when required vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            success, issues = validate_command._validate_environment_variables()
            assert not success
            assert any("API_KEY" in error for error in issues)

    def test_validate_configuration_files_with_valid_files(self, validate_command, mock_console):
        """Test configuration file validation with valid files."""
        fake_model = ModelSettings(
            model="gpt-5-mini",
            api_key="test-key",
            base_url="https://example.openai.azure.com/",
            authentication_method=AuthenticationMethod.TOKEN,
        )

        mock_settings = MagicMock()
        mock_settings.models = [fake_model]
        mock_settings.validate_configuration.return_value = None

        with patch(
            "ingenious.config.main_settings.IngeniousSettings",
            return_value=mock_settings,
        ):
            success, issues = validate_command._validate_configuration_files()
            assert success
            assert issues == []

    def test_validate_azure_connectivity_success(self, validate_command, mock_console):
        """Test Azure connectivity validation with successful connection."""
        # Mock the settings loading to return a valid model configuration
        mock_model = MagicMock()
        mock_model.base_url = "https://test.openai.azure.com/"
        mock_model.api_key = "test-key"
        mock_model.authentication_method = MagicMock()
        mock_model.authentication_method.value = "TOKEN"

        mock_settings = MagicMock()
        mock_settings.models = [mock_model]

        with patch(
            "ingenious.config.main_settings.IngeniousSettings",
            return_value=mock_settings,
        ):
            with patch.object(
                validate_command, "_validate_auth_credentials", return_value=(True, [])
            ):
                with patch(
                    "ingenious.cli.utilities.ValidationUtils.validate_url",
                    return_value=(True, ""),
                ):
                    with patch.object(
                        validate_command,
                        "_test_azure_connection",
                        return_value=(True, ""),
                    ):
                        success, issues = validate_command._validate_azure_connectivity()
                        assert success

    def test_validate_azure_connectivity_failure(self, validate_command, mock_console):
        """Test Azure connectivity validation with connection failure."""
        # Test case where no models are configured
        mock_settings = MagicMock()
        mock_settings.models = []

        with patch(
            "ingenious.config.main_settings.IngeniousSettings",
            return_value=mock_settings,
        ):
            success, issues = validate_command._validate_azure_connectivity()
            assert not success
            assert any("No Azure OpenAI models configured" in error for error in issues)

    def test_validate_workflows(self, validate_command, mock_console):
        """Test workflow validation."""
        # Mock the directory structure existence checks
        with patch("pathlib.Path.exists", return_value=True):
            with patch("importlib.util.find_spec") as mock_spec:
                mock_spec.return_value = MagicMock()  # Spec exists, indicating module can be found
                success, issues = validate_command._validate_workflows()
                assert success

    def test_validate_dependencies(self, validate_command, mock_console):
        """Test dependency validation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="package==1.0.0\n")
            success, issues = validate_command._validate_dependencies()
            assert success

    def test_validate_port_availability_open(self, validate_command, mock_console):
        """Test port availability when port is open."""
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.bind.return_value = None
            success, issues = validate_command._validate_port_availability()
            assert success

    def test_validate_port_availability_in_use(self, validate_command, mock_console):
        """Test port availability when port is in use."""
        # Mock the socket connection to succeed (port in use)
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.connect_ex.return_value = (
                0  # Connection successful = port in use
            )
            with patch("ingenious.config.config.get_config") as mock_config:
                mock_config.return_value.web_configuration.port = 8080
                success, issues = validate_command._validate_port_availability()
                assert not success
