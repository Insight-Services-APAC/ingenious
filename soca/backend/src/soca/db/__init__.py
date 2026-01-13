"""Database module for Cosmos DB operations."""

from soca.db.database import Database
from soca.db.templates import get_templates

# Global database instance
db = Database()

__all__ = [
    "Database",
    "db",
    "get_templates",
]
