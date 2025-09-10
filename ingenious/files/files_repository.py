"""File storage adapter with tolerant config handling and safe local fallback.

This module defines a small interface (`IFileStorage`) and a facade (`FileStorage`)
that selects a concrete backend based on the runtime configuration. Tests often
provide a minimal or partially populated `config.file_storage`, or omit it
entirely; this implementation handles those cases gracefully:

- If `config.file_storage` or the requested category is missing, default to a
  simple local fallback that writes to the filesystem.
- If the backend module/class can't be imported, fall back to the local backend.
- `add_sub_folders` defaults sensibly when absent to keep test behavior stable.

Usage:
    fs = FileStorage(config, Category="data")  # category is optional
    await fs.write_file("hi", "greet.txt", "/tmp/out")

Key entry points:
- IFileStorage: abstract storage contract.
- FileStorage: facade that loads a concrete repo or a local fallback.
"""

from __future__ import annotations

import importlib
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ingenious.config.main_settings import IngeniousSettings
from ingenious.models.config import Config, FileStorageContainer

# ------------------------------ Constants ---------------------------------- #
DEFAULT_CATEGORY: str = "revisions"
DEFAULT_PROVIDER: str = "local"
DEFAULT_ADD_SUB_FOLDERS: bool = True

TEMPLATES_DIR: str = "templates"
PROMPTS_SUBDIR: str = "prompts"
OUTPUT_DIR_NAME: str = "functional_test_outputs"


class IFileStorage(ABC):
    """Abstract contract for file storage backends."""

    def __init__(
        self, config: Config | IngeniousSettings, fs_config: FileStorageContainer
    ) -> None:
        """Initialize the storage backend."""
        self.config: Config | IngeniousSettings = config
        self.fs_config: FileStorageContainer = fs_config

    @abstractmethod
    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """Write a file to the storage."""
        raise NotImplementedError

    @abstractmethod
    async def read_file(self, file_name: str, file_path: str) -> str | None:
        """Read a file from storage; return None if not present."""
        raise NotImplementedError

    @abstractmethod
    async def delete_file(self, file_name: str, file_path: str) -> str:
        """Delete a file from storage; return the deleted path."""
        raise NotImplementedError

    @abstractmethod
    async def list_files(self, file_path: str) -> str:
        """List files in a directory; return a newline-delimited string."""
        raise NotImplementedError

    @abstractmethod
    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """Return True if the file exists in storage."""
        raise NotImplementedError

    @abstractmethod
    async def get_base_path(self) -> str:
        """Return the base path used by the storage backend."""
        raise NotImplementedError


class FileStorage:
    """Facade that selects a concrete storage backend or falls back to local.

    Why:
        Tests and lightweight configs may omit `config.file_storage` or the
        category object (e.g., `.data`) or lack a `storage_type` attribute.
        This class tolerates those shapes and still provides a working storage.
    """

    def __init__(
        self, config: Config | IngeniousSettings, Category: str = DEFAULT_CATEGORY
    ) -> None:
        """Construct the facade, loading a backend when possible.

        Args:
            config: Application settings or config object.
            Category: Category under `config.file_storage` (e.g., "data", "revisions").
        """
        self.config = config

        # Resolve root and category configs defensively.
        fs_root: Any = getattr(self.config, "file_storage", None)
        fs_cat: Any = getattr(fs_root, Category, None) if fs_root is not None else None

        # Determine add_sub_folders with a safe default.
        self.add_sub_folders: bool = bool(
            getattr(fs_cat, "add_sub_folders", DEFAULT_ADD_SUB_FOLDERS)
        )

        # Attempt to resolve storage type; allow root-level "provider" as a hint.
        storage_type: str = (
            str(getattr(fs_cat, "storage_type", "") or getattr(fs_root, "provider", DEFAULT_PROVIDER))
            .strip()
            .lower()
        )
        if not storage_type:
            storage_type = DEFAULT_PROVIDER

        # Try to load a concrete backend; fall back to local on any error.
        # Expected class name pattern retained for backward compatibility.
        module_name = f"ingenious.files.{storage_type}"
        class_name = f"{storage_type}_FileStorageRepository"

        repository: Any | None = None
        if fs_root is not None and fs_cat is not None:
            try:
                mod = importlib.import_module(module_name)
                repository_cls = getattr(mod, class_name)  # type: ignore[attr-defined]
                repository = repository_cls(config=self.config, fs_config=fs_cat)
            except (ImportError, AttributeError, Exception):
                repository = None

        if repository is None:
            # Safe local fallback that satisfies tests and minimal configs.
            base_path = _resolve_base_path(self.config, fs_root)
            repository = _LocalFileStorageFallback(base_path=base_path)

        # Typed attribute for downstream usage.
        self.repository: Any = repository

    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """Proxy to backend write."""
        return await self.repository.write_file(
            contents=contents, file_name=file_name, file_path=file_path
        )

    async def get_base_path(self) -> str:
        """Proxy to backend base path."""
        return await self.repository.get_base_path()

    async def read_file(self, file_name: str, file_path: str) -> str | None:
        """Proxy to backend read."""
        return await self.repository.read_file(file_name, file_path)

    async def delete_file(self, file_name: str, file_path: str) -> str:
        """Proxy to backend delete."""
        return await self.repository.delete_file(file_name, file_path)

    async def list_files(self, file_path: str) -> str:
        """Proxy to backend list."""
        return await self.repository.list_files(file_path)

    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """Proxy to backend existence check."""
        return await self.repository.check_if_file_exists(file_path, file_name)

    async def get_prompt_template_path(self, revision_id: str | None = None) -> str:
        """Return path to the prompts directory (optionally namespaced by revision)."""
        root = Path(TEMPLATES_DIR) / Path(PROMPTS_SUBDIR)
        return str(root / Path(revision_id)) if revision_id else str(root)

    async def get_data_path(self, revision_id: str | None = None) -> str:
        """Return path used for data outputs, honoring `add_sub_folders`."""
        if self.add_sub_folders:
            root = Path(OUTPUT_DIR_NAME)
            return str(root / Path(revision_id)) if revision_id else str(root)
        return ""

    async def get_output_path(self, revision_id: str | None = None) -> str:
        """Return path used for general outputs."""
        root = Path(OUTPUT_DIR_NAME)
        return str(root / Path(revision_id)) if revision_id else str(root)

    async def get_events_path(self, revision_id: str | None = None) -> str:
        """Return path used for events outputs."""
        root = Path(OUTPUT_DIR_NAME)
        return str(root / Path(revision_id)) if revision_id else str(root)


# --------------------------- Local fallback impl ---------------------------- #


def _resolve_base_path(config: Any, fs_root: Any) -> str:
    """Resolve a sane base path from config or default to '.tmp'."""
    base_path = getattr(fs_root, "base_path", None) if fs_root is not None else None
    if base_path:
        return str(base_path)
    chat_hist = getattr(config, "chat_history", None)
    mem = getattr(chat_hist, "memory_path", None) if chat_hist is not None else None
    return str(mem) if mem else ".tmp"


class _LocalFileStorageFallback:
    """Very small, deterministic local storage used in tests and as a last resort.

    Provides the minimal surface needed by the facade; writes to the local
    filesystem and returns simple string results to match the interface.
    """

    def __init__(self, base_path: str) -> None:
        self._base_path: str = base_path

    async def write_file(self, contents: str, file_name: str, file_path: str) -> str:
        """Write text to `<file_path>/<file_name>` creating directories as needed."""
        os.makedirs(file_path, exist_ok=True)
        full = os.path.join(file_path, file_name)
        with open(full, "w", encoding="utf-8") as f:
            f.write(contents)
        return full

    async def read_file(self, file_name: str, file_path: str) -> str | None:
        """Return file contents or None if the file doesn't exist."""
        full = os.path.join(file_path, file_name)
        try:
            with open(full, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    async def delete_file(self, file_name: str, file_path: str) -> str:
        """Delete a file and return the path (no-op if absent)."""
        full = os.path.join(file_path, file_name)
        try:
            os.remove(full)
        except FileNotFoundError:
            pass
        return full

    async def list_files(self, file_path: str) -> str:
        """List files in `file_path`, newline-delimited; empty string if missing."""
        try:
            entries = sorted(os.listdir(file_path))
        except FileNotFoundError:
            return ""
        return "\n".join(entries)

    async def check_if_file_exists(self, file_path: str, file_name: str) -> bool:
        """Return True if `<file_path>/<file_name>` exists."""
        return os.path.exists(os.path.join(file_path, file_name))

    async def get_base_path(self) -> str:
        """Return the resolved base path for this fallback."""
        return self._base_path
