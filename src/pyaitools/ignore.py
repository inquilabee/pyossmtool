"""Resolve and apply unified ignore profiles and paths for quality checks."""

from __future__ import annotations

import json
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
        for item in spec.ignore_profile:
            if item not in seen_profiles:
                seen_profiles.add(item)
                profiles.append(item)
        for item in spec.ignore_paths:
            if item not in seen_paths:
                seen_paths.add(item)
                paths.append(item)
    return IgnoreSpec(ignore_profile=profiles, ignore_paths=paths)


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
        IgnoreSpec(
            ignore_profile=suite.ignore_profile if suite else [],
            ignore_paths=suite.ignore_paths if suite else [],
        ),
        IgnoreSpec(
            ignore_profile=project_config.ignore_profile if project_config else [],
            ignore_paths=project_config.ignore_paths if project_config else [],
        ),
        IgnoreSpec(
            ignore_profile=check.ignore_profile if check else [],
            ignore_paths=check.ignore_paths if check else [],
        ),
        IgnoreSpec(
            ignore_profile=check_ref.ignore_profile if check_ref else [],
            ignore_paths=check_ref.ignore_paths if check_ref else [],
        ),
    )

    profile_files: list[str] = []
    for rel in merged.ignore_profile:
        path = (project_root / rel).resolve()
        if path.is_file():
            profile_files.append(str(path))

    path_patterns = [_normalize_pattern(pattern) for pattern in merged.ignore_paths]
    return EffectiveIgnores(profile_files=profile_files, path_patterns=path_patterns)


def filter_findings(findings: list, ignores: EffectiveIgnores) -> list:
    from pyaitools.models import Finding

    filtered: list[Finding] = []
    for finding in findings:
        if not isinstance(finding, Finding):
            filtered.append(finding)
            continue
        if finding.location and finding.location.file:
            if ignores.is_ignored(finding.location.file):
                continue
        filtered.append(finding)
    return filtered


def materialize_for_tool(
    tool_id: str,
    ignores: EffectiveIgnores,
    *,
    project_root: Path,
    check_id: str,
    base_config_path: Path | None = None,
) -> ToolIgnoreMaterial:
    patterns = _all_patterns(ignores)
    if not patterns:
        return ToolIgnoreMaterial()

    cache_dir = project_root / ".pyaitools" / "cache" / "ignores" / check_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    if tool_id == "ruff":
        argv = []
        for pattern in patterns:
            argv.extend(["--extend-exclude", pattern])
        return ToolIgnoreMaterial(argv=argv)

    if tool_id == "ty":
        config_path = cache_dir / "ty.toml"
        lines = ["[tool.ty]", "exclude = ["]
        lines.extend(f'  "{pattern}",' for pattern in patterns)
        lines.append("]")
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return ToolIgnoreMaterial(argv=["--config", str(config_path)], config_path=config_path)

    if tool_id in {"bandit"}:
        argv: list[str] = []
        for pattern in patterns:
            argv.extend(["-x", pattern])
        return ToolIgnoreMaterial(argv=argv)

    if tool_id == "semgrep":
        argv = []
        for pattern in patterns:
            argv.extend(["--exclude", pattern])
        return ToolIgnoreMaterial(argv=argv)

    if tool_id in {"deadcode", "vulture"}:
        argv = []
        for pattern in patterns:
            argv.append(f"--exclude={pattern}")
        return ToolIgnoreMaterial(argv=argv)

    if tool_id == "pytest":
        argv = []
        for pattern in patterns:
            argv.extend(["--ignore", pattern])
        return ToolIgnoreMaterial(argv=argv)

    if tool_id == "codespell":
        skip_file = cache_dir / "codespell.skip"
        skip_file.write_text("\n".join(patterns) + "\n", encoding="utf-8")
        return ToolIgnoreMaterial(argv=["--skip", str(skip_file)], skip_file=skip_file)

    if tool_id == "yamllint":
        config_path = cache_dir / "yamllint.yaml"
        overlay = _merge_yaml_config(
            base_config_path,
            {"ignore": _patterns_as_yaml_block(patterns)},
        )
        config_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
        return ToolIgnoreMaterial(argv=["-c", str(config_path)], config_path=config_path)

    if tool_id == "yamlfmt":
        config_path = cache_dir / "yamlfmt.yaml"
        overlay = _merge_yaml_config(
            base_config_path,
            {"exclude": patterns},
        )
        config_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
        return ToolIgnoreMaterial(argv=["-conf", str(config_path)], config_path=config_path)

    if tool_id == "jscpd":
        config_path = cache_dir / "jscpd.json"
        payload = {"ignore": patterns}
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return ToolIgnoreMaterial(argv=["--config", str(config_path)], config_path=config_path)

    # Tools without native exclude flags rely on post-filtering.
    return ToolIgnoreMaterial()


def ignore_env(ignores: EffectiveIgnores, project_root: Path) -> dict[str, str]:
    profiles = [
        str((project_root / rel).resolve())
        for rel in _profile_rel_paths(ignores, project_root)
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
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("!"):
            continue
        patterns.append(stripped)
    return patterns


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
    base: dict = {}
    if base_path and base_path.exists():
        loaded = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            base = loaded

    merged = dict(base)
    for key, value in overlay.items():
        if key == "ignore" and "ignore" in merged:
            existing = str(merged["ignore"]).strip().splitlines()
            new_lines = str(value).strip().splitlines()
            combined = list(dict.fromkeys([*existing, *new_lines]))
            merged["ignore"] = _patterns_as_yaml_block(combined)
        elif key == "exclude" and "exclude" in merged:
            existing = list(merged["exclude"]) if isinstance(merged["exclude"], list) else []
            new_items = value if isinstance(value, list) else [value]
            merged["exclude"] = list(dict.fromkeys([*existing, *new_items]))
        else:
            merged[key] = value
    return merged


def bundled_tool_ignore_patterns(tool_id: str) -> list[str]:
    """Static bundled defaults merged before suite/project ignores."""
    if tool_id == "deadcode":
        return ["**/models.py"]
    return []


def ignores_from_env(project_root: Path | None = None) -> EffectiveIgnores:
    """Build ignores from PYAITOOLS_IGNORE_* environment variables (script gates)."""
    import os

    profile_files = [
        item.strip()
        for item in os.environ.get("PYAITOOLS_IGNORE_PROFILES", "").splitlines()
        if item.strip()
    ]
    path_patterns = [
        _normalize_pattern(item)
        for item in os.environ.get("PYAITOOLS_IGNORE_PATHS", "").splitlines()
        if item.strip()
    ]
    root = (project_root or Path.cwd()).resolve()
    resolved_profiles: list[str] = []
    for profile in profile_files:
        path = Path(profile)
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            resolved_profiles.append(str(path.resolve()))
    return EffectiveIgnores(profile_files=resolved_profiles, path_patterns=path_patterns)
