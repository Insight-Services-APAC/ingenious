#!/usr/bin/env python3
"""
Configuration Migration Script for Ingenious

This script helps migrate from the old YAML-based configuration system
to the new pydantic-settings based system that uses environment variables.

Usage:
    python scripts/migrate_config.py --yaml-file config.yml --output .env
    python scripts/migrate_config.py --yaml-file config.yml --output .env.example

Features:
- Reads existing YAML configuration files
- Converts settings to environment variable format
- Generates .env files with proper INGENIOUS_ prefixes
- Provides helpful comments explaining each setting
- Validates the conversion by loading the new settings
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


def flatten_dict(
    data: Dict[str, Any], parent_key: str = "", separator: str = "__"
) -> Dict[str, Any]:
    """
    Flatten a nested dictionary into a flat dictionary with composite keys.

    Args:
        data: The dictionary to flatten
        parent_key: The parent key prefix
        separator: The separator to use between key levels

    Returns:
        Flattened dictionary
    """
    items: list[tuple[str, Any]] = []
    for key, value in data.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key

        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, separator).items())
        elif isinstance(value, list):
            # Handle lists specially for pydantic-settings
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    items.extend(
                        flatten_dict(item, f"{new_key}__{i}", separator).items()
                    )
                else:
                    items.append((f"{new_key}__{i}", str(item)))
        else:
            items.append((new_key, str(value) if value is not None else ""))

    return dict(items)


def convert_yaml_to_env_vars(yaml_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Convert YAML configuration data to environment variable format.

    Args:
        yaml_data: The parsed YAML data

    Returns:
        Dictionary of environment variable names to values
    """
    # Flatten the YAML data
    flat_data = flatten_dict(yaml_data)

    # Convert to INGENIOUS_ prefixed environment variables
    env_vars = {}
    for key, value in flat_data.items():
        # Convert to uppercase and add INGENIOUS_ prefix
        env_key = f"INGENIOUS_{key.upper()}"
        env_vars[env_key] = str(value)

    return env_vars


def get_setting_description(key: str) -> str:
    """
    Get a helpful description for a configuration setting.

    Args:
        key: The environment variable key

    Returns:
        Description string
    """
    descriptions = {
        "INGENIOUS_PROFILE": "Profile name for environment-specific settings",
        "INGENIOUS_MODELS__0__MODEL": "AI model name (e.g., 'gpt-4o-mini', 'gpt-3.5-turbo')",
        "INGENIOUS_MODELS__0__API_KEY": "API key for the AI model service",
        "INGENIOUS_MODELS__0__BASE_URL": "Base URL for the AI model API",
        "INGENIOUS_MODELS__0__API_VERSION": "API version for Azure OpenAI",
        "INGENIOUS_MODELS__0__DEPLOYMENT": "Azure OpenAI deployment name",
        "INGENIOUS_MODELS__0__API_TYPE": "API type (usually 'rest')",
        "INGENIOUS_CHAT_HISTORY__DATABASE_TYPE": "Database type: 'sqlite' or 'azuresql'",
        "INGENIOUS_CHAT_HISTORY__DATABASE_PATH": "Path to SQLite database file",
        "INGENIOUS_CHAT_HISTORY__DATABASE_CONNECTION_STRING": "Azure SQL connection string",
        "INGENIOUS_CHAT_HISTORY__MEMORY_PATH": "Path for memory storage",
        "INGENIOUS_LOGGING__ROOT_LOG_LEVEL": "Root logger level: debug, info, warning, error",
        "INGENIOUS_LOGGING__LOG_LEVEL": "Application logger level: debug, info, warning, error",
        "INGENIOUS_WEB_CONFIGURATION__IP_ADDRESS": "IP address to bind web server",
        "INGENIOUS_WEB_CONFIGURATION__PORT": "Port number for web server",
        "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE": "Enable web authentication",
        "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__USERNAME": "Username for basic auth",
        "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__PASSWORD": "Password for basic auth",
        "INGENIOUS_CHAINLIT_CONFIGURATION__ENABLE": "Enable Chainlit chat interface",
        "INGENIOUS_PROMPT_TUNER__ENABLE": "Enable prompt tuning interface",
        "INGENIOUS_TOOL_SERVICE__ENABLE": "Enable external tool service",
        "INGENIOUS_CHAT_SERVICE__TYPE": "Chat service type (usually 'multi_agent')",
        "INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE": "Storage type for revisions: 'local' or 'azure'",
        "INGENIOUS_FILE_STORAGE__DATA__STORAGE_TYPE": "Storage type for data: 'local' or 'azure'",
    }

    # Return specific description if available, otherwise generate a generic one
    if key in descriptions:
        return descriptions[key]

    # Generate description based on key pattern
    if "API_KEY" in key:
        return "API key for service authentication"
    elif "URL" in key or "ENDPOINT" in key:
        return "Service endpoint URL"
    elif "DATABASE" in key:
        return "Database configuration setting"
    elif "ENABLE" in key:
        return "Enable/disable feature flag"
    elif "PATH" in key:
        return "File or directory path"
    else:
        return "Configuration setting"


def write_env_file(
    env_vars: Dict[str, str], output_file: Path, include_comments: bool = True
) -> None:
    """
    Write environment variables to a .env file.

    Args:
        env_vars: Dictionary of environment variables
        output_file: Path to output file
        include_comments: Whether to include helpful comments
    """
    with open(output_file, "w") as f:
        if include_comments:
            f.write("# Ingenious Configuration\n")
            f.write("# Generated from YAML configuration migration\n")
            f.write(
                "# See: https://docs.pydantic.dev/latest/concepts/pydantic_settings/\n\n"
            )

        # Group related settings together
        sections: dict[str, list[tuple[str, str]]] = {
            "Profile Settings": [],
            "Model Configuration": [],
            "Chat History": [],
            "Logging": [],
            "Web Configuration": [],
            "Services": [],
            "File Storage": [],
            "Other": [],
        }

        for key, value in sorted(env_vars.items()):
            if "PROFILE" in key:
                sections["Profile Settings"].append((key, value))
            elif "MODELS" in key:
                sections["Model Configuration"].append((key, value))
            elif "CHAT_HISTORY" in key:
                sections["Chat History"].append((key, value))
            elif "LOGGING" in key:
                sections["Logging"].append((key, value))
            elif "WEB_CONFIGURATION" in key:
                sections["Web Configuration"].append((key, value))
            elif any(
                service in key
                for service in [
                    "CHAINLIT",
                    "PROMPT_TUNER",
                    "TOOL_SERVICE",
                    "CHAT_SERVICE",
                ]
            ):
                sections["Services"].append((key, value))
            elif "FILE_STORAGE" in key:
                sections["File Storage"].append((key, value))
            else:
                sections["Other"].append((key, value))

        for section_name, items in sections.items():
            if not items:
                continue

            if include_comments:
                f.write(f"# {section_name}\n")

            for key, value in items:
                if include_comments:
                    description = get_setting_description(key)
                    f.write(f"# {description}\n")

                # Quote values that contain spaces or special characters
                if " " in value or any(
                    char in value for char in ["#", "=", "\n", "\r"]
                ):
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f"{key}={value}\n")

                if include_comments:
                    f.write("\n")

            if include_comments:
                f.write("\n")


def validate_migration(env_file: Path) -> bool:
    """
    Validate the migration by trying to load the new configuration.

    Args:
        env_file: Path to the generated .env file

    Returns:
        True if validation passes, False otherwise
    """
    try:
        # Add the parent directory to the Python path
        parent_dir = Path(__file__).parent.parent
        sys.path.insert(0, str(parent_dir))

        from ingenious.config import IngeniousSettings

        # Load settings with the new .env file
        settings = IngeniousSettings(_env_file=str(env_file))

        print(f"✓ Successfully loaded configuration with {len(settings.models)} models")
        return True

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate YAML configuration to environment variables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --yaml-file config.yml --output .env
  %(prog)s --yaml-file config.yml --output .env.example --no-comments
  %(prog)s --yaml-file config.yml --validate-only
        """,
    )

    parser.add_argument(
        "--yaml-file",
        type=Path,
        required=True,
        help="Path to the YAML configuration file to migrate",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".env.migrated"),
        help="Output .env file path (default: .env.migrated)",
    )

    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Don't include helpful comments in the output file",
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the YAML file, don't generate output",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated configuration by loading it",
    )

    args = parser.parse_args()

    # Check if YAML file exists
    if not args.yaml_file.exists():
        print(f"Error: YAML file '{args.yaml_file}' not found")
        sys.exit(1)

    # Load YAML file
    try:
        with open(args.yaml_file, "r") as f:
            yaml_data = yaml.safe_load(f)
        print(f"✓ Successfully loaded YAML configuration from '{args.yaml_file}'")
    except Exception as e:
        print(f"Error reading YAML file: {e}")
        sys.exit(1)

    if args.validate_only:
        print("YAML file is valid")
        return

    # Convert to environment variables
    env_vars = convert_yaml_to_env_vars(yaml_data)
    print(
        f"✓ Converted {len(env_vars)} configuration settings to environment variables"
    )

    # Write .env file
    try:
        write_env_file(env_vars, args.output, include_comments=not args.no_comments)
        print(f"✓ Generated environment file: '{args.output}'")
    except Exception as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)

    # Validate if requested
    if args.validate:
        print("\nValidating generated configuration...")
        if validate_migration(args.output):
            print("✓ Configuration migration completed successfully!")
        else:
            print("✗ Configuration validation failed. Please check the generated file.")
            sys.exit(1)
    else:
        print("\nMigration completed! To validate, run:")
        print(
            f"  python -c \"from ingenious.config import IngeniousSettings; IngeniousSettings(_env_file='{args.output}')\""
        )

    print("\nNext steps:")
    print(f"1. Review the generated file: {args.output}")
    print("2. Copy settings to your .env file")
    print("3. Set any placeholder values to real credentials")
    print(
        '4. Test with: uv run python -c "from ingenious.config.config import get_config; get_config()"'
    )


if __name__ == "__main__":
    main()
