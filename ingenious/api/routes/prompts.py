from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing_extensions import Annotated

import ingenious.dependencies as ingen_deps
from ingenious.core.structured_logging import get_logger
from ingenious.files.files_repository import FileStorage
from ingenious.utils.namespace_utils import discover_workflows, normalize_workflow_name
from ingenious.utils.revision_names import generate_revision_id, normalize_revision_id

logger = get_logger(__name__)
router = APIRouter()


class UpdatePromptRequest(BaseModel):
    content: str


class CreateRevisionRequest(BaseModel):
    revision_id: Optional[str] = None


async def _get_existing_revision_ids(fs: FileStorage) -> Set[str]:
    """
    Helper function to get existing revision IDs from the templates directory.
    """
    try:
        # Get the base templates/prompts path
        base_template_path = await fs.get_prompt_template_path()

        # List all directories in the templates/prompts folder
        revision_dirs: List[str] = await fs.list_directories(
            file_path=base_template_path
        )

        # Convert list to set
        revision_ids = set(revision_dirs) if revision_dirs else set()

        # If no revisions found via directory listing, try to discover from workflows
        if not revision_ids:
            config = ingen_deps.get_config()
            workflows = discover_workflows(
                include_builtin=config.chat_service.enable_builtin_workflows
            )
            for workflow in workflows:
                # Check if this workflow has prompts
                workflow_path = await fs.get_prompt_template_path(workflow)
                try:
                    workflow_files = await fs.list_files(file_path=workflow_path)
                    if workflow_files:
                        revision_ids.add(workflow)
                except Exception:
                    pass

        return revision_ids
    except Exception as e:
        logger.error("Error getting existing revision IDs", error=str(e), exc_info=True)
        return set()


@router.get("/revisions/list")
async def list_revisions(
    request: Request,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> Dict[str, Any]:
    """
    List all available revisions (workflow directories) in the prompt templates.
    """
    try:
        revision_ids = await _get_existing_revision_ids(fs)

        return {
            "revisions": sorted(list(revision_ids)),
            "count": len(revision_ids),
            "discovered_from": "template_directories" if revision_ids else "workflows",
        }
    except Exception as e:
        logger.error("Error listing revisions", error=str(e), exc_info=True)
        return {"revisions": [], "count": 0, "error": str(e)}


@router.get("/workflows/list")
async def list_workflows_for_prompts(
    request: Request,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> Dict[str, Any]:
    """
    List all available workflows that have prompt templates.
    """
    try:
        config = ingen_deps.get_config()
        workflows = discover_workflows(
            include_builtin=config.chat_service.enable_builtin_workflows
        )
        workflows_with_prompts = []

        for workflow in workflows:
            # Try both underscore and hyphenated formats
            workflow_variants = [workflow]
            if "_" in workflow:
                workflow_variants.append(workflow.replace("_", "-"))
            elif "-" in workflow:
                workflow_variants.append(workflow.replace("-", "_"))

            found_prompts = False
            for variant in workflow_variants:
                try:
                    # Check if this workflow has prompts
                    workflow_path = await fs.get_prompt_template_path(variant)
                    workflow_files = await fs.list_files(file_path=workflow_path)
                    if workflow_files:
                        prompt_files = [
                            f for f in workflow_files if f.endswith((".md", ".jinja"))
                        ]
                        if prompt_files:
                            workflows_with_prompts.append(
                                {
                                    "workflow": workflow,
                                    "revision_id": variant,
                                    "prompt_count": len(prompt_files),
                                    "prompt_files": prompt_files,
                                }
                            )
                            found_prompts = True
                            break
                except Exception as e:
                    logger.debug(
                        "Error checking workflow",
                        workflow_variant=variant,
                        error=str(e),
                    )
                    continue

            # If we couldn't find prompts, still include the workflow
            if not found_prompts:
                workflows_with_prompts.append(
                    {
                        "workflow": workflow,
                        "revision_id": workflow,
                        "prompt_count": 0,
                        "prompt_files": [],
                        "note": "No prompts found or path not accessible",
                    }
                )

        return {
            "workflows": workflows_with_prompts,
            "count": len(workflows_with_prompts),
            "total_workflows_discovered": len(workflows),
        }
    except Exception as e:
        logger.error("Error listing workflows", error=str(e), exc_info=True)
        return {"workflows": [], "count": 0, "error": str(e)}


@router.get("/prompts/list/{revision_id}")
async def list_prompts_enhanced(
    revision_id: str,
    request: Request,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> Dict[str, Any]:
    """
    Enhanced prompt listing with better metadata and error handling.
    """
    try:
        # Normalize the revision_id to handle both hyphenated and underscored formats
        normalized_revision_id = normalize_workflow_name(revision_id)

        # Try both original and normalized revision IDs
        revision_ids_to_try = [revision_id, normalized_revision_id]
        if revision_id != normalized_revision_id:
            revision_ids_to_try.append(revision_id.replace("_", "-"))

        files = []
        successful_revision_id = None

        for rid in revision_ids_to_try:
            try:
                prompt_template_folder = await fs.get_prompt_template_path(
                    revision_id=rid
                )
                file_list = await fs.list_files(file_path=prompt_template_folder)

                # Filter to get only template files
                potential_files = []
                for f in file_list:
                    if f and f.endswith((".md", ".jinja")):
                        # For Azure Blob Storage, extract just the filename
                        filename = f.split("/")[-1] if "/" in f else f
                        potential_files.append(filename)

                if potential_files:
                    files = sorted(potential_files)
                    successful_revision_id = rid
                    break

            except Exception as e:
                logger.debug(
                    "Failed to list prompts for revision", revision_id=rid, error=str(e)
                )
                continue

        if not files and not successful_revision_id:
            # Return empty result with helpful information
            return {
                "revision_id": revision_id,
                "normalized_revision_id": normalized_revision_id,
                "files": [],
                "count": 0,
                "attempted_revisions": revision_ids_to_try,
                "note": "No prompt templates found for this revision. Check if the revision exists or if templates have been uploaded.",
            }

        return {
            "revision_id": revision_id,
            "actual_revision_used": successful_revision_id,
            "normalized_revision_id": normalized_revision_id,
            "files": files,
            "count": len(files),
            "attempted_revisions": revision_ids_to_try,
        }

    except Exception as e:
        logger.error(
            "Error listing prompts for revision",
            revision_id=revision_id,
            error=str(e),
            exc_info=True,
        )
        return {"revision_id": revision_id, "files": [], "count": 0, "error": str(e)}


@router.get("/prompts/view/{revision_id}/{filename}")
async def view(
    revision_id: str,
    filename: str,
    request: Request,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> str:
    prompt_template_folder = await fs.get_prompt_template_path(revision_id=revision_id)
    content = await fs.read_file(file_name=filename, file_path=prompt_template_folder)
    return content


@router.post("/prompts/update/{revision_id}/{filename}")
async def update(
    revision_id: str,
    filename: str,
    request: Request,
    update_request: UpdatePromptRequest,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> Dict[str, str]:
    prompt_template_folder = await fs.get_prompt_template_path(revision_id=revision_id)
    try:
        await fs.write_file(
            contents=update_request.content,
            file_name=filename,
            file_path=prompt_template_folder,
        )
        return {"message": "File updated successfully"}
    except Exception as e:
        logger.error(
            "Failed to update file",
            revision_id=revision_id,
            filename=filename,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to update file")


@router.post("/revisions/create")
async def create_revision(
    request: Request,
    create_request: CreateRevisionRequest,
    username: Annotated[str, Depends(ingen_deps.get_conditional_security)],
    fs: FileStorage = Depends(ingen_deps.get_file_storage_revisions),
) -> Dict[str, Any]:
    """
    Create a new revision with templates copied from the configured original templates.

    If no revision_id is provided, generates a funny name like 'cosmic-ninja-a1b2c3d4'.
    If revision_id is provided but conflicts, appends incremental numbers like 'my-workflow-1'.
    """
    try:
        # Early validation of revision_id format if provided
        if create_request.revision_id:
            try:
                # Validate format without conflict checking yet
                normalize_revision_id(create_request.revision_id)
            except ValueError as e:
                logger.warning(
                    "Invalid revision_id format provided",
                    revision_id=create_request.revision_id,
                    error=str(e),
                )
                raise HTTPException(
                    status_code=400, detail=f"Invalid revision_id format: {str(e)}"
                )

        # Only proceed with file operations after basic validation passes
        existing_revision_ids = await _get_existing_revision_ids(fs)

        # Generate the final revision ID
        final_revision_id = generate_revision_id(
            create_request.revision_id, list(existing_revision_ids)
        )

        # Get source templates from configured original templates revision
        config = ingen_deps.get_config()
        original_templates_revision = config.file_storage.revisions.original_templates
        source_path = await fs.get_prompt_template_path(original_templates_revision)
        try:
            raw_source_files = await fs.list_files(file_path=source_path)
        except Exception as e:
            logger.error(
                "Failed to access original templates directory",
                source_path=source_path,
                original_templates_revision=original_templates_revision,
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail="Original template directory not found or inaccessible",
            )

        # Parse source files - handle both newline-separated and Python list string formats
        source_files: List[str] = []
        for f in raw_source_files:
            if f and f.endswith((".md", ".jinja")):
                filename = f.split("/")[-1] if "/" in f else f
                source_files.append(filename)

        if not source_files:
            logger.error(
                "No template files found in original templates",
                source_path=source_path,
                original_templates_revision=original_templates_revision,
            )
            raise HTTPException(
                status_code=500,
                detail=f"No template files found in {original_templates_revision} directory",
            )

        # Get destination path for new revision
        dest_path = await fs.get_prompt_template_path(final_revision_id)

        # Copy each template file
        copied_files = []
        failed_files = []

        for filename in source_files:
            try:
                # Read from source
                content = await fs.read_file(file_name=filename, file_path=source_path)

                # Write to destination
                await fs.write_file(
                    contents=content,
                    file_name=filename,
                    file_path=dest_path,
                )

                copied_files.append(filename)

            except Exception as e:
                logger.debug(
                    "Failed to copy template file",
                    filename=filename,
                    error=str(e),
                )
                failed_files.append(filename)

        # Check if any files were successfully copied
        if not copied_files:
            raise HTTPException(
                status_code=500, detail="Failed to copy any template files"
            )

        logger.debug(
            "Successfully created revision",
            revision_id=final_revision_id,
            copied_files_count=len(copied_files),
        )

        response_data = {
            "revision_id": final_revision_id,
            "message": "Revision created successfully",
            "template_count": len(copied_files),
            "copied_files": copied_files,
        }

        # Include failed files info if any
        if failed_files:
            response_data["partial_success"] = True
            response_data["failed_files"] = failed_files
            response_data["warning"] = (
                f"Failed to copy {len(failed_files)} template files"
            )

        return response_data

    except HTTPException:
        # Re-raise HTTP exceptions (these are intentional)
        raise
    except Exception as e:
        logger.error(
            "Unexpected error creating revision",
            requested_id=create_request.revision_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Internal server error while creating revision"
        )
