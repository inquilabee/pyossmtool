"""Storage package for report-server persistence."""

from shipgate.server.storage.base import MAX_RUNS, Storage
from shipgate.server.storage.sqlite import SqliteStorage

__all__ = ["MAX_RUNS", "Storage", "SqliteStorage"]
