"""Storage backends"""

from .base import Storage, StorageConfig, create_storage, register_storage
from .git import (
    GitDirectStorage,
    GitDirectStorageConfig,
    # Backward compatibility exports
    git_push_to_remote,
    ensure_bare_repo_exists,
    get_remote_url,
)

__all__ = [
    "Storage",
    "StorageConfig",
    "create_storage",
    "register_storage",
    "GitDirectStorage",
    "GitDirectStorageConfig",
    # Backward compatibility
    "git_push_to_remote",
    "ensure_bare_repo_exists",
    "get_remote_url",
]
