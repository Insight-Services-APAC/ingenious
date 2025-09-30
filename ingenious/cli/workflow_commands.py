"""
Workflow-related CLI commands for Insight Ingenious.

This module contains commands for managing and viewing workflow requirements.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from typing_extensions import Annotated


def register_commands(app: typer.Typer, console: Console) -> None:
    """Register workflow-related commands with the typer app."""

    @app.command(
        name="workflows", help="Show available workflows and their requirements"
    )
    def workflows(
        workflow: Annotated[
            str,
            typer.Argument(
                help="Specific workflow to check, or 'all' to list everything"
            ),
        ] = "all",
    ) -> None:
        """
        📋 Display available conversation workflows and their configuration requirements.

        Use this command to understand what external services and configuration
        are needed for each workflow before attempting to use them.

        Examples:
          ingen workflows                      # List all available workflows
          ingen workflows classification-agent # Show specific workflow details
          ingen workflows knowledge-base-agent # Show requirements for KB agent
        """
        return workflow_requirements(workflow=workflow)

    # Keep old command for backward compatibility
    @app.command(hidden=True)
    def workflow_requirements(
        workflow: Annotated[
            str,
            typer.Argument(
                help="Workflow name to check requirements for, or 'all' to list all workflows"
            ),
        ] = "all",
    ) -> None:
        """
        Show configuration requirements for conversation workflows.

        Use this command to understand what external services and configuration
        are needed for each workflow before attempting to use them.
        """
        workflows = {
            "classification-agent": {
                "description": "Simple text classification and routing (easier alternative to bike-insights)",
                "category": "✅ Simple Text Processing",
                "requirements": ["Azure OpenAI"],
                "config_needed": [
                    "Environment: set INGENIOUS_MODELS__0__* (model, api_key, base_url)",
                ],
                "optional": [],
                "example_curl": """curl -X POST http://localhost:80/api/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_prompt": "Analyze this customer feedback: Great product!",
    "conversation_flow": "classification_agent"
  }'""",
                "note": "Simple text classification - try this if bike-insights seems too complex",
            },
            "bike-insights": {
                "description": "⭐ **HELLO WORLD WORKFLOW** - Multi-agent bike sales analysis (RECOMMENDED START HERE!)",
                "category": "⭐ Hello World Workflow",
                "requirements": ["Azure OpenAI"],
                "config_needed": [
                    "Environment: set INGENIOUS_MODELS__0__* (model, api_key, base_url)",
                ],
                "optional": [],
                "example_curl": """curl -X POST http://localhost:80/api/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_prompt": "{\\"stores\\": [{\\"name\\": \\"Hello Store\\", \\"location\\": \\"NSW\\", \\"bike_sales\\": [{\\"product_code\\": \\"HELLO-001\\", \\"quantity_sold\\": 1, \\"sale_date\\": \\"2023-04-01\\", \\"year\\": 2023, \\"month\\": \\"April\\", \\"customer_review\\": {\\"rating\\": 5.0, \\"comment\\": \\"Perfect introduction to Ingenious!\\"}}], \\"bike_stock\\": []}], \\"revision_id\\": \\"hello-1\\", \\"identifier\\": \\"world\\"}",
    "conversation_flow": "bike-insights"
  }'""",
                "note": "🌟 This is the recommended first workflow - showcases multi-agent coordination!",
            },
            "knowledge-base-agent": {
                "description": "Search and retrieve information from knowledge bases",
                "category": "🔍 Requires Azure Search",
                "requirements": ["Azure OpenAI", "Azure Cognitive Search"],
                "config_needed": [
                    "Environment: configure INGENIOUS_MODELS__0__*",
                    "Environment: configure INGENIOUS_AZURE_SEARCH_SERVICES__0__* (endpoint, key, index)",
                    "Pre-configured search indexes",
                ],
                "optional": [],
            },
            "sql-manipulation-agent": {
                "description": "Execute SQL queries based on natural language",
                "category": "📊 Requires Database",
                "requirements": ["Azure OpenAI", "Database (Azure SQL or SQLite)"],
                "config_needed": [
                    "For Azure SQL: set INGENIOUS_AZURE_SQL_SERVICES__* values",
                    "For Local SQLite: set INGENIOUS_LOCAL_SQL_DB__DATABASE_PATH (optional)",
                ],
                "optional": [],
            },
            # Legacy names for backward compatibility
            "classification_agent": {
                "description": "✅ Simple text processing - Use 'classification-agent' or 'classification_agent' (both work!)",
                "category": "✅ Simple Text Processing",
                "requirements": ["Azure OpenAI"],
                "config_needed": [
                    "Environment: set INGENIOUS_MODELS__0__* (model, api_key, base_url)",
                ],
                "optional": [],
                "example_curl": """curl -X POST http://localhost:80/api/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{"user_prompt": "Hello, can you help me?", "conversation_flow": "classification_agent"}'""",
                "note": "Simple alternative if bike-insights seems too complex",
            },
            "bike_insights": {
                "description": "⭐ **HELLO WORLD WORKFLOW** - Use 'bike-insights' or 'bike_insights' (both work!)",
                "category": "⭐ Hello World Workflow",
                "requirements": ["Azure OpenAI"],
                "config_needed": [
                    "Environment: set INGENIOUS_MODELS__0__* (model, api_key, base_url)",
                ],
                "optional": [],
                "example_curl": """curl -X POST http://localhost:80/api/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_prompt": "{\\"stores\\": [{\\"name\\": \\"Hello Store\\", \\"location\\": \\"NSW\\", \\"bike_sales\\": [{\\"product_code\\": \\"HELLO-001\\", \\"quantity_sold\\": 1, \\"sale_date\\": \\"2023-04-01\\", \\"year\\": 2023, \\"month\\": \\"April\\", \\"customer_review\\": {\\"rating\\": 5.0, \\"comment\\": \\"Perfect introduction!\\"}}], \\"bike_stock\\": []}], \\"revision_id\\": \\"hello-1\\", \\"identifier\\": \\"world\\"}",
    "conversation_flow": "bike-insights"
  }'""",
                "note": "🌟 This is the Hello World workflow - try it first!",
            },
            "knowledge_base_agent": {
                "description": "⚠️  DEPRECATED: Use 'knowledge-base-agent' instead",
                "category": "🔍 Requires Azure Search",
                "requirements": ["Azure OpenAI", "Azure Cognitive Search"],
                "config_needed": ["See 'knowledge-base-agent' for details"],
                "optional": [],
            },
            "sql_manipulation_agent": {
                "description": "⚠️  DEPRECATED: Use 'sql-manipulation-agent' instead",
                "category": "📊 Requires Database",
                "requirements": ["Azure OpenAI", "Database (Azure SQL or SQLite)"],
                "config_needed": ["See 'sql-manipulation-agent' for details"],
                "optional": [],
            },
        }

        if workflow == "all":
            console.print(
                "\n[bold blue]📋 INSIGHT INGENIOUS WORKFLOW REQUIREMENTS[/bold blue]\n"
            )

            # Group by category, prioritizing new hyphenated names
            categories: dict[str, list[tuple[str, dict[str, Any]]]] = {}
            for name, info in workflows.items():
                # Skip deprecated workflow names in the main listing
                if "DEPRECATED" in info["description"]:
                    continue

                cat = str(info["category"])
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append((name, info))

            for category, workflow_list in categories.items():
                console.print(f"[bold]{category}[/bold]")
                for name, info in workflow_list:
                    console.print(f"  • [cyan]{name}[/cyan]: {info['description']}")
                console.print()

            console.print(
                '[bold yellow]💡 TIP:[/bold yellow] Start with bike-insights (the "Hello World" of Ingenious)'
            )
            console.print(
                "[bold yellow]📖 DOCS:[/bold yellow] See docs/workflows/README.md for complete configuration guide"
            )
            console.print(
                "[bold yellow]🧪 TEST:[/bold yellow] Try 'ingen workflows bike-insights' for a working example"
            )

        elif workflow in workflows:
            info = workflows[workflow]
            console.print(
                f"\n[bold blue]📋 {workflow.upper()} REQUIREMENTS[/bold blue]\n"
            )
            console.print(f"[bold]Description:[/bold] {info['description']}")
            console.print(f"[bold]Category:[/bold] {info['category']}")
            console.print("[bold]External Services Needed:[/bold]")
            for req in info["requirements"]:
                console.print(f"  • {req}")
            console.print("\n[bold]Configuration Required:[/bold]")
            for config in info["config_needed"]:
                console.print(f"  • {config}")
            if info["optional"]:
                console.print("\n[bold]Optional:[/bold]")
                for opt in info["optional"]:
                    console.print(f"  • {opt}")

            # Show special note if available
            if "note" in info:
                console.print(f"\n[bold yellow]⚠️  Note:[/bold yellow] {info['note']}")

            console.print("\n[bold yellow]🧪 TEST COMMAND:[/bold yellow]")
            if "example_curl" in info:
                console.print(info["example_curl"])
            else:
                console.print("curl -X POST http://localhost:80/api/v1/chat \\")
                console.print('  -H "Content-Type: application/json" \\')
                console.print(
                    f'  -d \'{"user_prompt": "Hello", "conversation_flow": "{workflow}"}\''
                )

        else:
            console.print(f"[bold red]❌ Unknown workflow: {workflow}[/bold red]")
            console.print("\n[bold]Available workflows:[/bold]")
            # Show only the current (non-deprecated) workflow names
            for name, info in workflows.items():
                if "DEPRECATED" not in info["description"]:
                    console.print(f"  • {name}")
            console.print(
                "\nUse 'ingen workflows' to see all workflows with descriptions"
            )
