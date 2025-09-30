import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from typing_extensions import Annotated

from ingenious.core.structured_logging import get_logger
from ingenious.models.http_error import HTTPError
from ingenious.services import auth_dependencies
from ingenious.services import fastapi_dependencies as ingen_deps
from ingenious.utils.namespace_utils import (
    discover_workflows,
    get_workflow_metadata,
    normalize_workflow_name,
)

logger = get_logger(__name__)
router = APIRouter()


@router.get(
    "/workflow-status/{workflow_name}",
    responses={
        200: {"model": dict, "description": "Workflow configuration status"},
        400: {"model": HTTPError, "description": "Bad Request"},
        404: {"model": HTTPError, "description": "Workflow Not Found"},
    },
)
async def workflow_status(
    workflow_name: str,
    request: Request,
    auth_user: Annotated[str, Depends(auth_dependencies.get_auth_user)],
) -> Dict[str, Any]:
    """
    Check the configuration status of a specific workflow.

    Returns information about whether the workflow is properly configured
    and what external services or configuration might be missing.
    """
    try:
        config = ingen_deps.get_config()

        # Normalize workflow name to handle both hyphenated and underscored formats
        normalized_workflow_name = normalize_workflow_name(workflow_name)

        # Discover available workflows dynamically
        available_workflows = discover_workflows(
            include_builtin=config.chat_service.enable_builtin_workflows
        )

        # Check against normalized name
        if normalized_workflow_name not in available_workflows:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown workflow: {workflow_name} (normalized: {normalized_workflow_name}). Available: {available_workflows}",
            )

        # Get workflow metadata
        requirements = get_workflow_metadata(normalized_workflow_name)
        missing_config = []
        configured = True

        # Check basic configuration
        if not config.models or len(config.models) == 0:
            missing_config.append("models: No models configured")
            configured = False
        else:
            # Check if model has required fields from environment configuration
            model = config.models[0]
            if not hasattr(model, "api_key") or not model.api_key:
                missing_config.append(
                    "models.api_key: Missing environment configuration"
                )
                configured = False
            if not hasattr(model, "base_url") or not model.base_url:
                missing_config.append(
                    "models.base_url: Missing environment configuration"
                )
                configured = False

        if not config.chat_service or config.chat_service.type != "multi_agent":
            missing_config.append("chat_service.type: Must be 'multi_agent'")
            configured = False

        # Check workflow-specific requirements
        if "azure_search_services" in requirements["required_config"]:
            if (
                not config.azure_search_services
                or len(config.azure_search_services) == 0
            ):
                missing_config.append("azure_search_services: Not configured")
                configured = False
            else:
                search_service = config.azure_search_services[0]
                if not search_service.endpoint:
                    missing_config.append("azure_search_services.endpoint: Missing")
                    configured = False
                if not hasattr(search_service, "key") or not search_service.key:
                    missing_config.append(
                        "azure_search_services.key: Missing environment configuration"
                    )
                    configured = False

        if "local_sql_db" in requirements["required_config"]:
            if not hasattr(config, "local_sql_db") or not config.local_sql_db:
                missing_config.append("local_sql_db: Not configured")
                configured = False
            else:
                if not config.local_sql_db.database_path:
                    missing_config.append("local_sql_db.database_path: Missing")
                    configured = False
                if not config.local_sql_db.sample_csv_path:
                    missing_config.append("local_sql_db.sample_csv_path: Missing")
                    configured = False

        # For SQL manipulation agent, check either Azure SQL or local is configured
        if workflow_name == "sql_manipulation_agent":
            has_azure_sql = (
                hasattr(config, "azure_sql_services")
                and config.azure_sql_services
                and hasattr(config.azure_sql_services, "database_connection_string")
                and config.azure_sql_services.database_connection_string
            )
            has_local_sql = (
                hasattr(config, "local_sql_db")
                and config.local_sql_db
                and config.local_sql_db.database_path
            )

            if not has_azure_sql and not has_local_sql:
                missing_config.append(
                    "database: Neither Azure SQL nor local SQLite configured"
                )
                configured = False

        return {
            "workflow": workflow_name,
            "description": requirements["description"],
            "category": requirements["category"],
            "configured": configured,
            "missing_config": missing_config,
            "required_config": requirements["required_config"],
            "external_services": requirements["external_services"],
            "ready": configured,
            "test_command": f'curl -X POST http://localhost:{config.web_configuration.port}/api/v1/chat -H "Content-Type: application/json" -d \'{{"user_prompt": "Hello", "conversation_flow": "{workflow_name}"}}\'',
            "documentation": "See docs/workflows/README.md for detailed setup instructions",
        }

    except Exception as e:
        logger.error(
            "Error in workflow status check",
            workflow_name=workflow_name,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/workflows",
    responses={
        200: {"model": dict, "description": "List all workflows and their status"},
        400: {"model": HTTPError, "description": "Bad Request"},
    },
)
async def list_workflows(
    request: Request,
    auth_user: Annotated[str, Depends(auth_dependencies.get_auth_user)],
) -> Dict[str, Any]:
    """
    List all available workflows and their configuration status.
    Supports both hyphenated (bike-insights) and underscored (bike_insights) naming formats.
    Dynamically discovers workflows from all namespaces.
    """
    try:
        config = ingen_deps.get_config()

        # Dynamically discover all available workflows
        discovered_workflows = discover_workflows(
            include_builtin=config.chat_service.enable_builtin_workflows
        )

        workflow_statuses = []
        for workflow in discovered_workflows:
            # Get status for each workflow
            status = await workflow_status(workflow, request, auth_user)

            # Add supported naming formats to the status
            hyphenated_name = workflow.replace("_", "-")
            status["supported_names"] = (
                [workflow, hyphenated_name]
                if workflow != hyphenated_name
                else [workflow]
            )

            workflow_statuses.append(status)

        # Group by category
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for status in workflow_statuses:
            category = status["category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(status)

        return {
            "workflows": workflow_statuses,
            "by_category": by_category,
            "summary": {
                "total": len(discovered_workflows),
                "configured": len([w for w in workflow_statuses if w["configured"]]),
                "unconfigured": len(
                    [w for w in workflow_statuses if not w["configured"]]
                ),
            },
            "naming_note": "Workflows support both hyphenated (bike-insights) and underscored (bike_insights) naming formats",
        }

    except Exception as e:
        logger.error("Error listing workflows", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route(
    "/diagnostic",
    methods=["GET", "OPTIONS"],
    responses={
        200: {"model": dict, "description": "Diagnostic information"},
        400: {"model": HTTPError, "description": "Bad Request"},
        406: {"model": HTTPError, "description": "Not Acceptable"},
        413: {"model": HTTPError, "description": "Payload Too Large"},
    },
)
async def diagnostic(
    request: Request,
    auth_user: Annotated[str, Depends(auth_dependencies.get_auth_user)],
) -> Dict[str, Any]:
    if request.method == "OPTIONS":
        return {"Allow": "GET, OPTIONS"}

    try:
        diagnostic = {}

        config = ingen_deps.get_config()
        revisions_storage = ingen_deps.get_file_storage_revisions(config=config)
        data_storage = ingen_deps.get_file_storage_data(config=config)

        prompt_dir = Path(await revisions_storage.get_base_path()) / Path(
            await revisions_storage.get_prompt_template_path()
        )

        data_dir = Path(await data_storage.get_base_path()) / Path(
            await data_storage.get_data_path()
        )

        output_dir = Path(await revisions_storage.get_base_path()) / Path(
            await revisions_storage.get_output_path()
        )

        events_dir = Path(await revisions_storage.get_base_path()) / Path(
            await revisions_storage.get_events_path()
        )

        diagnostic["Prompt Directory"] = prompt_dir
        diagnostic["Data Directory"] = data_dir
        diagnostic["Output Directory"] = output_dir
        diagnostic["Events Directory"] = events_dir

        return diagnostic

    except Exception as e:
        logger.error("Error in diagnostic check", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    responses={
        200: {"model": dict, "description": "System health status"},
        503: {"model": HTTPError, "description": "Service Unavailable"},
    },
)
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for monitoring system status.

    Returns basic system information and configuration status.
    Useful for load balancers, monitoring systems, and quick validation.
    """
    try:
        start_time = time.time()

        # Check basic configuration availability
        try:
            _ = ingen_deps.get_config()
            config_status = "ok"
        except Exception as e:
            logger.warning("Configuration check failed", error=str(e))
            config_status = "error"

        # Profile system is deprecated - no longer check for profiles
        profile_status = "ok"  # Always OK since profiles are no longer used

        response_time = round((time.time() - start_time) * 1000, 2)  # ms

        # Determine overall status
        overall_status = (
            "healthy"
            if config_status == "ok" and profile_status == "ok"
            else "degraded"
        )

        health_data = {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "response_time_ms": response_time,
            "components": {"configuration": config_status, "profile": profile_status},
            "version": "1.0.0",  # Could be pulled from package info
            "uptime": "available",  # Could track actual uptime if needed
        }

        # Return 503 if any critical components are down
        if overall_status == "degraded":
            raise HTTPException(status_code=503, detail=health_data)

        return health_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Health check failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            },
        )
