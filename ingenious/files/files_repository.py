import importlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

from ingenious.config.main_settings import IngeniousSettings
from ingenious.models.config import Config, FileStorageContainer


class IFileStorage(ABC):
    def __init__(
        self, config: Union[Config, IngeniousSettings], fs_config: FileStorageContainer
    ):
        self.config: Union[Config, IngeniousSettings] = config
        self.fs_config: FileStorageContainer = fs_config

    @abstractmethod
    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """writes a file to the file storage"""
        pass

    @abstractmethod
    async def read_file(self, file_name: str, file_path: str) -> str:
        """reads a file to the file storage"""
        pass

    @abstractmethod
    async def delete_file(self, file_name: str, file_path: str) -> str:
        """deletes a file to the file storage"""
        pass

    @abstractmethod
    async def list_files(self, file_path: str) -> List[str]:
        """lists files in the file storage"""
        pass

    @abstractmethod
    async def list_directories(self, file_path: str) -> List[str]:
        """lists directories in the file storage"""
        pass

    @abstractmethod
    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """checks if a file exists in the file storage"""
        pass

    @abstractmethod
    async def get_base_path(self) -> str:
        """returns the base path of the file storage"""
        pass


class FileStorage:
    def __init__(
        self, config: Union[Config, IngeniousSettings], Category: str = "revisions"
    ):
        self.config = config
        self.add_sub_folders = getattr(
            self.config.file_storage, Category
        ).add_sub_folders

        # Get the file storage config for the specified category
        fs_config = getattr(self.config.file_storage, Category)
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
        return await self.repository.write_file(
            contents=contents, file_name=file_name, file_path=file_path
        )

    async def get_base_path(self) -> str:
        return await self.repository.get_base_path()

    async def read_file(self, file_name: str, file_path: str) -> str:
        return await self.repository.read_file(file_name, file_path)

    async def delete_file(self, file_name: str, file_path: str) -> str:
        return await self.repository.delete_file(file_name, file_path)

    async def list_files(self, file_path: str) -> List[str]:
        return await self.repository.list_files(file_path)

    async def list_directories(self, file_path: str) -> List[str]:
        return await self.repository.list_directories(file_path)

    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        return await self.repository.check_if_file_exists(file_path, file_name)

    async def get_prompt_template_path(self, revision_id: str | None = None) -> str:
        if revision_id:
            template_path = str(Path("templates") / Path("prompts") / Path(revision_id))
        else:
            template_path = str(Path("templates") / Path("prompts"))
        return template_path

    async def get_data_path(self, revision_id: str | None = None) -> str:
        if self.add_sub_folders:
            if revision_id:
                template_path = str(Path("functional_test_outputs") / Path(revision_id))
            else:
                template_path = str(Path("functional_test_outputs"))
        else:
            template_path = ""
        return template_path

    async def get_output_path(self, revision_id: str | None = None) -> str:
        if revision_id:
            template_path = str(Path("functional_test_outputs") / Path(revision_id))
        else:
            template_path = str(Path("functional_test_outputs"))
        return template_path

    async def get_events_path(self, revision_id: str | None = None) -> str:
        if revision_id:
            template_path = str(Path("functional_test_outputs") / Path(revision_id))
        else:
            template_path = str(Path("functional_test_outputs"))
        return template_path
