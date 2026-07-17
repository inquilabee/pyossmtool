"""Resolve installed or catalog versions for Tool docs page."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shipgate.models import EnvMode, InstallMethod, ToolDef
from shipgate.resolver import BinaryResolver

_VERSION_ATTEMPTS = ("--version", "-version", "-V", "version")
_TIMEOUT_S = 3.0
_LEADING_NAME = re.compile(r"^[A-Za-z0-9._-]+\s+")
_VERSION_LINE = re.compile(
    r"(?:^|\b)version[:\s,]+[vV]?(?P<version>\d+\.\d+(?:\.\d+)?(?:[.\w-]*)?)",
    re.IGNORECASE,
)
_SEMVER = re.compile(r"\d+\.\d+(?:\.\d+)?(?:[.\w-]*)?")
_PACKAGE_NAME = re.compile(r"^([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class ToolDocsRow:
    id: str
    name: str
    description: str
    documentation_url: str | None
    version: str


def tool_docs_rows(tools: list[ToolDef], primary_root: Path) -> list[ToolDocsRow]:
    resolver = BinaryResolver(project_root=primary_root, tools_root=primary_root)
    return [
        ToolDocsRow(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            documentation_url=tool.documentation_url,
            version=_resolve_version(tool, resolver, primary_root),
        )
        for tool in tools
    ]


def _resolve_version(tool: ToolDef, resolver: BinaryResolver, primary_root: Path) -> str:
    installed = _installed_version(tool, resolver)
    if installed:
        return installed
    pip_version = _pip_show_version(tool, primary_root)
    if pip_version:
        return pip_version
    if tool.install.version:
        return tool.install.version
    return _requirement_version(tool) or "—"


def _requirement_version(tool: ToolDef) -> str | None:
    requirement = _package_requirement(tool.install.package)
    if requirement and requirement.lower() not in {tool.binary.lower(), tool.id.lower()}:
        return requirement
    return None


def _installed_version(tool: ToolDef, resolver: BinaryResolver) -> str | None:
    try:
        binary = resolver.resolve(tool, EnvMode.MANAGED)
    except FileNotFoundError:
        return None
    for flag in _VERSION_ATTEMPTS:
        parsed = _run_version_command(binary, flag, tool.binary)
        if parsed:
            return parsed
    return None


def _run_version_command(binary: Path, flag: str, binary_name: str) -> str | None:
    command = [str(binary), flag]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if not text:
        return None
    return _parse_version_from_output(text, binary_name)


def _parse_version_from_output(text: str, binary_name: str) -> str | None:
    for line in text.splitlines():
        version = _version_from_line(line.strip(), binary_name)
        if version:
            return version
    return _semver_fallback(text, binary_name)


def _version_from_line(stripped: str, binary_name: str) -> str | None:
    if not stripped:
        return None
    match = _VERSION_LINE.search(stripped)
    if match:
        return _clean_version(match.group("version"))
    normalized = _normalize_version_line(stripped, binary_name)
    if not _is_plausible_version(normalized, binary_name):
        return None
    found = _SEMVER.search(normalized)
    return _clean_version(found.group(0)) if found else None


def _semver_fallback(text: str, binary_name: str) -> str | None:
    found = _SEMVER.search(text)
    if found and _is_plausible_version(found.group(0), binary_name):
        return _clean_version(found.group(0))
    return None


def _pip_show_version(tool: ToolDef, primary_root: Path) -> str | None:
    if tool.install.method != InstallMethod.PIP:
        return None
    package_name = _package_name(tool.install.package)
    if package_name is None:
        return None
    python = primary_root / ".shipgate" / "tools" / "venv" / "bin" / "python"
    if not python.is_file():
        return None
    output = _pip_show_output(python, package_name)
    return _pip_show_field(output) if output else None


def _pip_show_output(python: Path, package_name: str) -> str | None:
    try:
        completed = subprocess.run(
            [str(python), "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _pip_show_field(output: str) -> str | None:
    for line in output.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _package_name(package: str | None) -> str | None:
    if not package:
        return None
    match = _PACKAGE_NAME.match(package.strip())
    return match.group(1) if match else None


def _package_requirement(package: str | None) -> str | None:
    if not package:
        return None
    first = package.split()[0].strip()
    return first or None


def _normalize_version_line(line: str, binary_name: str) -> str:
    lowered = line.lower()
    prefix = binary_name.lower()
    if lowered.startswith(prefix + " "):
        return line[len(binary_name) :].strip()
    if lowered.startswith(prefix + "/"):
        return line[len(binary_name) + 1 :].strip()
    return _LEADING_NAME.sub("", line, count=1).strip() or line


def _clean_version(value: str) -> str:
    return value.lstrip("vV")


def _is_plausible_version(value: str, binary_name: str) -> bool:
    if not value or value.lower() == binary_name.lower():
        return False
    if "version is set by build process" in value.lower():
        return False
    return bool(_SEMVER.search(value))
