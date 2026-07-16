"""Resolve and apply unified ignore profiles and paths for quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pathspec
import yaml

from pyaitools.models import CheckDef, IgnoreSpec, ProjectConfig, SuiteCheckRef, SuiteDef


@dataclass
class ToolIgnoreMaterial:
    """Tool-specific ignore materialization output."""

    argv: list[str] = field(default_factory=list)
    config_path: Path | None = None
    skip_file: Path | None = None
    post_subcommand: bool = False


@dataclass
class EffectiveIgnores:
    """Merged ignore patterns for a single check run."""

    profile_files: list[str] = field(default_factory=list)
    path_patterns: list[str] = field(default_factory=list)
    _matcher: pathspec.PathSpec | None = field(default=None, repr=False)

    def matcher(self) -> pathspec.PathSpec:
        if self._matcher is None:
            patterns = list(self.path_patterns)
            for profile in self.profile_files:
                patterns.extend(_load_profile_patterns(Path(profile)))
            self._matcher = pathspec.PathSpec.from_lines("gitignore", patterns)
        return self._matcher

    def is_ignored(self, repo_relative_path: str) -> bool:
        normalized = _normalize_repo_path(repo_relative_path)
        if not normalized:
            return False
        return self.matcher().match_file(normalized)


def merge_ignore_specs(*specs: IgnoreSpec | None) -> IgnoreSpec:
    profiles: list[str] = []
    paths: list[str] = []
    seen_profiles: set[str] = set()
    seen_paths: set[str] = set()
    for spec in specs:
        if spec is None:
            continue
        _extend_unique(profiles, seen_profiles, spec.ignore_profile)
        _extend_unique(paths, seen_paths, spec.ignore_paths)
    return IgnoreSpec(ignore_profile=profiles, ignore_paths=paths)


def _extend_unique(target: list[str], seen: set[str], values: list[str]) -> None:
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        target.append(item)


def resolve_effective_ignores(
    project_root: Path,
    *,
    suite: SuiteDef | None = None,
    project_config: ProjectConfig | None = None,
    check_ref: SuiteCheckRef | None = None,
    check: CheckDef | None = None,
    bundled_patterns: list[str] | None = None,
) -> EffectiveIgnores:
    merged = merge_ignore_specs(
        IgnoreSpec(ignore_paths=bundled_patterns or []),
        _ignore_spec_from(suite),
        _ignore_spec_from(project_config),
        _ignore_spec_from(check),
        _ignore_spec_from(check_ref),
    )
    return _effective_from_merged(merged, project_root)


def _ignore_spec_from(source) -> IgnoreSpec:
    if source is None:
        return IgnoreSpec()
    return IgnoreSpec(ignore_profile=source.ignore_profile, ignore_paths=source.ignore_paths)


def _effective_from_merged(merged: IgnoreSpec, project_root: Path) -> EffectiveIgnores:
    profile_files = [
        str((project_root / rel).resolve())
        for rel in merged.ignore_profile
        if (project_root / rel).resolve().is_file()
    ]
    path_patterns = [_normalize_pattern(pattern) for pattern in merged.ignore_paths]
    return EffectiveIgnores(profile_files=profile_files, path_patterns=path_patterns)


def filter_findings(findings: list, ignores: EffectiveIgnores) -> list:

    return [finding for finding in findings if _keep_finding(finding, ignores)]


def _keep_finding(finding, ignores: EffectiveIgnores) -> bool:
    from pyaitools.models import Finding

    if not isinstance(finding, Finding):
        return True
    if not finding.location or not finding.location.file:
        return True
    return not ignores.is_ignored(finding.location.file)


def materialize_for_tool(
    tool_id: str,
    ignores: EffectiveIgnores,
    *,
    project_root: Path,
    check_id: str,
    base_config_path: Path | None = None,
) -> ToolIgnoreMaterial:
    from pyaitools.ignore_materialize import materialize_for_tool as _materialize

    return _materialize(
        tool_id,
        ignores,
        project_root=project_root,
        check_id=check_id,
        base_config_path=base_config_path,
    )


def ignore_env(ignores: EffectiveIgnores, project_root: Path) -> dict[str, str]:
    profiles = [
        str((project_root / rel).resolve()) for rel in _profile_rel_paths(ignores, project_root)
    ]
    env: dict[str, str] = {}
    if profiles:
        env["PYAITOOLS_IGNORE_PROFILES"] = "\n".join(profiles)
    if ignores.path_patterns:
        env["PYAITOOLS_IGNORE_PATHS"] = "\n".join(ignores.path_patterns)
    return env


def _profile_rel_paths(ignores: EffectiveIgnores, project_root: Path) -> list[str]:
    rels: list[str] = []
    for path in ignores.profile_files:
        try:
            rels.append(str(Path(path).resolve().relative_to(project_root.resolve())))
        except ValueError:
            rels.append(path)
    return rels


def _all_patterns(ignores: EffectiveIgnores) -> list[str]:
    patterns = list(ignores.path_patterns)
    for profile in ignores.profile_files:
        patterns.extend(_load_profile_patterns(Path(profile)))
    deduped: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        normalized = _normalize_pattern(pattern)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _load_profile_patterns(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        pattern
        for line in path.read_text(encoding="utf-8").splitlines()
        if (pattern := _profile_line_pattern(line)) is not None
    ]


def _profile_line_pattern(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("!"):
        return None
    return stripped


def _normalize_pattern(pattern: str) -> str:
    pattern = pattern.strip().replace("\\", "/")
    if pattern.startswith("./"):
        pattern = pattern[2:]
    return pattern.rstrip("/") if not pattern.endswith("/") else pattern


def _normalize_repo_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _patterns_as_yaml_block(patterns: list[str]) -> str:
    return "\n".join(patterns) + ("\n" if patterns else "")


def _merge_yaml_config(base_path: Path | None, overlay: dict) -> dict:
    merged = _load_yaml_dict(base_path)
    for key, value in overlay.items():
        merged[key] = _merge_yaml_value(merged, key, value)
    return merged


def _load_yaml_dict(base_path: Path | None) -> dict:
    if not base_path or not base_path.exists():
        return {}
    loaded = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _merge_yaml_value(merged: dict, key: str, value) -> object:
    if key == "ignore" and "ignore" in merged:
        return _merge_ignore_block(merged["ignore"], value)
    if key == "exclude" and "exclude" in merged:
        return _merge_exclude_list(merged["exclude"], value)
    return value


def _merge_ignore_block(existing_value, value) -> str:
    existing = str(existing_value).strip().splitlines()
    new_lines = str(value).strip().splitlines()
    return _patterns_as_yaml_block(list(dict.fromkeys([*existing, *new_lines])))


def _merge_exclude_list(existing_value, value) -> list:
    existing = list(existing_value) if isinstance(existing_value, list) else []
    new_items = value if isinstance(value, list) else [value]
    return list(dict.fromkeys([*existing, *new_items]))


def bundled_tool_ignore_patterns(tool_id: str) -> list[str]:
    """Static bundled defaults merged before suite/project ignores."""
    if tool_id == "deadcode":
        return ["**/models.py"]
    return []


def ignores_from_env(project_root: Path | None = None) -> EffectiveIgnores:
    """Build ignores from PYAITOOLS_IGNORE_* environment variables (script gates)."""
    import os

    root = (project_root or Path.cwd()).resolve()
    profile_files = _resolve_env_profiles(root, os.environ.get("PYAITOOLS_IGNORE_PROFILES", ""))
    path_patterns = _env_path_patterns(os.environ.get("PYAITOOLS_IGNORE_PATHS", ""))
    return EffectiveIgnores(profile_files=profile_files, path_patterns=path_patterns)


def _env_path_patterns(text: str) -> list[str]:
    return [_normalize_pattern(item) for item in text.splitlines() if item.strip()]


def _resolve_env_profiles(root: Path, text: str) -> list[str]:
    resolved: list[str] = []
    for item in text.splitlines():
        profile = item.strip()
        if not profile:
            continue
        path = Path(profile)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            resolved.append(str(path.resolve()))
    return resolved
