"""Per-tool ignore pattern materialization driven by ToolDef.ignore."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pyaitools.ignore import EffectiveIgnores, ToolIgnoreMaterial, _all_patterns, _merge_yaml_config
from pyaitools.models import ExtendFrom, IgnoreKind, ToolDef, ToolIgnoreSpec


def materialize_for_tool(
    tool: ToolDef,
    ignores: EffectiveIgnores,
    *,
    project_root: Path,
    check_id: str,
    base_config_path: Path | None = None,
) -> ToolIgnoreMaterial:
    patterns = _all_patterns(ignores)
    if not patterns or tool.ignore is None:
        return ToolIgnoreMaterial()

    cache_dir = project_root / ".pyaitools" / "cache" / "ignores" / check_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return _materialize(tool.ignore, patterns, project_root, cache_dir, base_config_path)


def _materialize(
    spec: ToolIgnoreSpec,
    patterns: list[str],
    project_root: Path,
    cache_dir: Path,
    base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    if spec.kind == IgnoreKind.FLAG_PAIRS:
        return _flag_pairs(spec, patterns)
    if spec.kind == IgnoreKind.PREFIX:
        return _prefix_flags(spec, patterns)
    if spec.kind == IgnoreKind.SKIP_FILE:
        return _skip_file(spec, patterns, cache_dir)
    if spec.kind == IgnoreKind.CONFIG_OVERLAY:
        return _config_overlay(spec, patterns, project_root, cache_dir, base_config_path)
    return ToolIgnoreMaterial()


def _flag_pairs(spec: ToolIgnoreSpec, patterns: list[str]) -> ToolIgnoreMaterial:
    if not spec.flag:
        return ToolIgnoreMaterial()
    argv: list[str] = []
    for pattern in patterns:
        argv.extend([spec.flag, pattern])
    return ToolIgnoreMaterial(argv=argv, post_subcommand=spec.post_subcommand)


def _prefix_flags(spec: ToolIgnoreSpec, patterns: list[str]) -> ToolIgnoreMaterial:
    if not spec.prefix:
        return ToolIgnoreMaterial()
    return ToolIgnoreMaterial(
        argv=[f"{spec.prefix}{pattern}" for pattern in patterns],
        post_subcommand=spec.post_subcommand,
    )


def _skip_file(spec: ToolIgnoreSpec, patterns: list[str], cache_dir: Path) -> ToolIgnoreMaterial:
    filename = spec.file or "ignores.skip"
    skip_file = cache_dir / filename
    skip_file.write_text("\n".join(patterns) + "\n", encoding="utf-8")
    flag = spec.flag or "--skip"
    return ToolIgnoreMaterial(
        argv=[flag, str(skip_file)],
        skip_file=skip_file,
        post_subcommand=spec.post_subcommand,
    )


def _config_overlay(
    spec: ToolIgnoreSpec,
    patterns: list[str],
    project_root: Path,
    cache_dir: Path,
    base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    filename = spec.file or f"ignores.{spec.format or 'txt'}"
    config_path = cache_dir / filename
    body = _overlay_body(spec, patterns, project_root, base_config_path)
    if body is None:
        return ToolIgnoreMaterial()
    config_path.write_text(body, encoding="utf-8")
    flag = spec.flag or "--config"
    return ToolIgnoreMaterial(
        argv=[flag, str(config_path)],
        config_path=config_path,
        post_subcommand=spec.post_subcommand,
    )


def _overlay_body(
    spec: ToolIgnoreSpec,
    patterns: list[str],
    project_root: Path,
    base_config_path: Path | None,
) -> str | None:
    if spec.format == "toml":
        return _toml_overlay(spec, patterns, project_root, base_config_path)
    if spec.format == "yaml":
        return _yaml_overlay(spec, patterns, base_config_path)
    if spec.format == "json":
        return _json_overlay(spec, patterns)
    return None


def _toml_overlay(
    spec: ToolIgnoreSpec,
    patterns: list[str],
    project_root: Path,
    base_config_path: Path | None,
) -> str:
    lines: list[str] = []
    extend_line = _toml_extend_line(spec, project_root, base_config_path)
    if extend_line:
        lines.append(extend_line)
    if spec.toml_table:
        lines.append(f"[{spec.toml_table}]")
    key = spec.key or "exclude"
    lines.append(f"{key} = [")
    lines.extend(f'  "{pattern}",' for pattern in patterns)
    lines.append("]")
    return "\n".join(lines) + "\n"


def _toml_extend_line(
    spec: ToolIgnoreSpec,
    project_root: Path,
    base_config_path: Path | None,
) -> str | None:
    extend_key = spec.extend_key or "extend"
    if spec.extend_from == ExtendFrom.BASE_CONFIG:
        return _extend_base_only(extend_key, base_config_path)
    if spec.extend_from == ExtendFrom.BASE_OR_PYPROJECT:
        return _extend_base_or_pyproject(extend_key, project_root, base_config_path)
    if spec.extend_from == ExtendFrom.PYPROJECT:
        return _extend_pyproject_list(extend_key, project_root)
    return None


def _extend_base_only(extend_key: str, base_config_path: Path | None) -> str | None:
    if base_config_path and base_config_path.exists():
        return f'{extend_key} = "{base_config_path}"'
    return None


def _extend_base_or_pyproject(
    extend_key: str, project_root: Path, base_config_path: Path | None
) -> str | None:
    base = _extend_base_only(extend_key, base_config_path)
    if base:
        return base
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        return f'{extend_key} = "{pyproject}"'
    return None


def _extend_pyproject_list(extend_key: str, project_root: Path) -> str | None:
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        return f'{extend_key} = ["{pyproject}"]'
    return None


def _yaml_overlay(spec: ToolIgnoreSpec, patterns: list[str], base_config_path: Path | None) -> str:
    key = spec.key or "exclude"
    if spec.key_style == "block":
        overlay = {key: "\n".join(patterns) + ("\n" if patterns else "")}
    else:
        overlay = {key: patterns}
    merged = _merge_yaml_config(base_config_path, overlay)
    return yaml.safe_dump(merged, sort_keys=False)


def _json_overlay(spec: ToolIgnoreSpec, patterns: list[str]) -> str:
    key = spec.key or "ignore"
    return json.dumps({key: patterns}, indent=2) + "\n"
