"""Canonical runtime paths and config filenames for shipgate."""

from __future__ import annotations

RUNTIME_DIR = ".shipgate"
LEGACY_RUNTIME_DIR = ".pyossmtool"
CONFIG_FILENAME = "shipgate.yaml"
LEGACY_CONFIG_FILENAME = "pyossmtool.yaml"

PROJECT_CATALOG = f"{RUNTIME_DIR}/catalog"
PROJECT_SUITES = f"{RUNTIME_DIR}/suites"
PROJECT_GATES_DIR = f"{RUNTIME_DIR}/gates"
PROJECT_CHECKS_DIR = f"{PROJECT_CATALOG}/checks"
PROJECT_CONFIGS_DIR = f"{RUNTIME_DIR}/configs"
PROJECT_REPORTS_DIR = f"{RUNTIME_DIR}/reports"
PROJECT_CACHE_DIR = f"{RUNTIME_DIR}/cache"
PROJECT_TOOLS_DIR = f"{RUNTIME_DIR}/tools"
PROJECT_SERVER_DIR = f"{RUNTIME_DIR}/server"
PROJECT_WORKTREES_DIR = f"{RUNTIME_DIR}/worktrees"

SERVER_DB_FILENAME = "shipgate.db"
