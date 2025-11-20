"""File storage abstraction supporting both local and Azure Blob Storage."""

import importlib
from abc import ABC, abstractmethod
from pathlib import Path

from ingenious.config.models import FileStorageContainerSettings
from ingenious.config.settings import IngeniousSettings


class IFileStorage(ABC):
    """Abstract base class defining the file storage interface.

    Provides a common interface for file operations that can be implemented
    by different storage backends (local filesystem, Azure Blob Storage, etc.).
    """

    def __init__(self, config: IngeniousSettings, fs_config: FileStorageContainerSettings):
        """Initialize the file storage interface.

        Args:
            config: The ingenious settings configuration.
            fs_config: File storage container configuration.
        """
        self.config: IngeniousSettings = config
        self.fs_config: FileStorageContainerSettings = fs_config

    @abstractmethod
    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """Writes a file to the file storage."""
        pass

    @abstractmethod
    async def read_file(self, file_name: str, file_path: str) -> str:
        """Reads a file to the file storage."""
        pass

    @abstractmethod
    async def delete_file(self, file_name: str, file_path: str) -> str:
        """Deletes a file to the file storage."""
        pass

    @abstractmethod
    async def list_files(self, file_path: str) -> str:
        """Lists files in the file storage."""
        pass

    @abstractmethod
    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """Checks if a file exists in the file storage."""
        pass

    @abstractmethod
    async def get_base_path(self) -> str:
        """Returns the base path of the file storage."""
        pass


class FileStorage:
    """File storage facade that dynamically loads the appropriate storage backend.

    Acts as a factory and facade for file storage operations, automatically
    selecting and initializing the correct storage implementation (local or Azure)
    based on configuration settings.
    """

    def __init__(self, config: IngeniousSettings, category: str = "revisions"):
        """Initialize the FileStorage with configuration and category.

        Args:
            config: The ingenious settings configuration.
            category: The file storage category (e.g., 'revisions'). Defaults to 'revisions'.
        """
        self.config = config
        self.add_sub_folders = getattr(self.config.file_storage, category).add_sub_folders

        # Get the file storage config for the specified category
        fs_config = getattr(self.config.file_storage, category)
        storage_type = fs_config.storage_type

        # Build module name based on the category's storage type
        module_name = f"ingenious.files.{storage_type.lower()}"

        # Dynamically import the module based on the storage type
        class_name = f"{storage_type}_FileStorageRepository"

        try:
            module = importlib.import_module(module_name)
            repository_class = getattr(module, class_name)
            self.repository: IFileStorage = repository_class(
                config=self.config, fs_config=fs_config
            )

        except (ImportError, AttributeError) as e:
            raise ValueError(
                f"Unsupported File Storage client type: {module_name}.{class_name}"
            ) from e

    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """Write a file to the file storage.

        Args:
            contents: The content to write to the file.
            file_name: The name of the file.
            file_path: The path where the file should be written.

        Returns:
            A string indicating the result of the write operation.
        """
        return await self.repository.write_file(
            contents=contents, file_name=file_name, file_path=file_path
        )

    async def get_base_path(self) -> str:
        """Get the base path of the file storage.

        Returns:
            The base path string.
        """
        return await self.repository.get_base_path()

    async def read_file(self, file_name: str, file_path: str) -> str:
        """Read a file from the file storage.

        Args:
            file_name: The name of the file to read.
            file_path: The path where the file is located.

        Returns:
            The contents of the file as a string.
        """
        return await self.repository.read_file(file_name, file_path)

    async def delete_file(self, file_name: str, file_path: str) -> str:
        """Delete a file from the file storage.

        Args:
            file_name: The name of the file to delete.
            file_path: The path where the file is located.

        Returns:
            A string indicating the result of the delete operation.
        """
        return await self.repository.delete_file(file_name, file_path)

    async def list_files(self, file_path: str) -> str:
        """List all files in the specified path.

        Args:
            file_path: The path to list files from.

        Returns:
            A string representation of the files in the path.
        """
        return await self.repository.list_files(file_path)

    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """Check if a file exists in the file storage.

        Args:
            file_path: The path where the file should be located.
            file_name: The name of the file to check.

        Returns:
            True if the file exists, False otherwise.
        """
        return await self.repository.check_if_file_exists(file_path, file_name)

    async def get_prompt_template_path(self, revision_id: str | None = None) -> str:
        """Get the path for prompt templates.

        Args:
            revision_id: Optional revision ID to include in the path.

        Returns:
            The prompt template path string.
        """
        if revision_id:
            template_path = str(Path("templates") / Path("prompts") / Path(revision_id))
        else:
            template_path = str(Path("templates") / Path("prompts"))
        return template_path

    async def get_data_path(self, revision_id: str | None = None) -> str:
        """Get the path for functional test data.

        Args:
            revision_id: Optional revision ID to include in the path.

        Returns:
            The data path string, or empty string if sub-folders are disabled.
        """
        if self.add_sub_folders:
            if revision_id:
                template_path = str(Path("functional_test_outputs") / Path(revision_id))
            else:
                template_path = str(Path("functional_test_outputs"))
        else:
            template_path = ""
        return template_path

    async def get_output_path(self, revision_id: str | None = None) -> str:
        """Get the path for functional test outputs.

        Args:
            revision_id: Optional revision ID to include in the path.

        Returns:
            The output path string.
        """
        if revision_id:
            template_path = str(Path("functional_test_outputs") / Path(revision_id))
        else:
            template_path = str(Path("functional_test_outputs"))
        return template_path

    async def get_events_path(self, revision_id: str | None = None) -> str:
        """Get the path for events data.

        Args:
            revision_id: Optional revision ID to include in the path.

        Returns:
            The events path string.
        """
        if revision_id:
            template_path = str(Path("functional_test_outputs") / Path(revision_id))
        else:
            template_path = str(Path("functional_test_outputs"))
        return template_path
