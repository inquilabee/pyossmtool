"""Per-tool ignore pattern materialization for native quality tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import yaml

from pyaitools.ignore import EffectiveIgnores, ToolIgnoreMaterial, _all_patterns, _merge_yaml_config


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
    handler = _HANDLERS.get(tool_id)
    if handler is None:
        return ToolIgnoreMaterial()
    return handler(patterns, project_root, cache_dir, base_config_path)


def _materialize_ruff(
    patterns: list[str],
    project_root: Path,
    cache_dir: Path,
    base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    config_path = cache_dir / "ruff.toml"
    lines: list[str] = []
    if base_config_path and base_config_path.exists():
        lines.append(f'extend = "{base_config_path}"')
    elif (project_root / "pyproject.toml").exists():
        lines.append(f'extend = "{project_root / "pyproject.toml"}"')
    lines.append("extend-exclude = [")
    lines.extend(f'  "{pattern}",' for pattern in patterns)
    lines.append("]")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ToolIgnoreMaterial(argv=["--config", str(config_path)], config_path=config_path)


def _materialize_ty(
    patterns: list[str],
    project_root: Path,
    cache_dir: Path,
    _base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    config_path = cache_dir / "ty.toml"
    lines: list[str] = []
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        lines.append(f'extends = ["{pyproject}"]')
    lines.extend(["[tool.ty]", "exclude = ["])
    lines.extend(f'  "{pattern}",' for pattern in patterns)
    lines.append("]")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ToolIgnoreMaterial(
        argv=["--config", str(config_path)],
        config_path=config_path,
        post_subcommand=True,
    )


def _materialize_flag_pairs(
    patterns: list[str],
    flag: str,
) -> ToolIgnoreMaterial:
    argv: list[str] = []
    for pattern in patterns:
        argv.extend([flag, pattern])
    return ToolIgnoreMaterial(argv=argv)


def _materialize_prefix_flags(
    patterns: list[str],
    prefix: str,
) -> ToolIgnoreMaterial:
    return ToolIgnoreMaterial(argv=[f"{prefix}{pattern}" for pattern in patterns])


def _materialize_codespell(
    patterns: list[str],
    _project_root: Path,
    cache_dir: Path,
    _base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    skip_file = cache_dir / "codespell.skip"
    skip_file.write_text("\n".join(patterns) + "\n", encoding="utf-8")
    return ToolIgnoreMaterial(argv=["--skip", str(skip_file)], skip_file=skip_file)


def _materialize_yamllint(
    patterns: list[str],
    _project_root: Path,
    cache_dir: Path,
    base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    config_path = cache_dir / "yamllint.yaml"
    overlay = _merge_yaml_config(base_config_path, {"ignore": _patterns_as_yaml_block(patterns)})
    config_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
    return ToolIgnoreMaterial(argv=["-c", str(config_path)], config_path=config_path)


def _materialize_yamlfmt(
    patterns: list[str],
    _project_root: Path,
    cache_dir: Path,
    base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    config_path = cache_dir / "yamlfmt.yaml"
    overlay = _merge_yaml_config(base_config_path, {"exclude": patterns})
    config_path.write_text(yaml.safe_dump(overlay, sort_keys=False), encoding="utf-8")
    return ToolIgnoreMaterial(argv=["-conf", str(config_path)], config_path=config_path)


def _materialize_jscpd(
    patterns: list[str],
    _project_root: Path,
    cache_dir: Path,
    _base_config_path: Path | None,
) -> ToolIgnoreMaterial:
    config_path = cache_dir / "jscpd.json"
    config_path.write_text(json.dumps({"ignore": patterns}, indent=2) + "\n", encoding="utf-8")
    return ToolIgnoreMaterial(argv=["--config", str(config_path)], config_path=config_path)


def _patterns_as_yaml_block(patterns: list[str]) -> str:
    return "\n".join(patterns) + ("\n" if patterns else "")


_Handler = Callable[[list[str], Path, Path, Path | None], ToolIgnoreMaterial]

_HANDLERS: dict[str, _Handler] = {
    "ruff": _materialize_ruff,
    "ty": _materialize_ty,
    "bandit": lambda patterns, *_args: _materialize_flag_pairs(patterns, "-x"),
    "semgrep": lambda patterns, *_args: ToolIgnoreMaterial(
        argv=_materialize_flag_pairs(patterns, "--exclude").argv,
        post_subcommand=True,
    ),
    "deadcode": lambda patterns, *_args: _materialize_prefix_flags(patterns, "--exclude="),
    "vulture": lambda patterns, *_args: _materialize_prefix_flags(patterns, "--exclude="),
    "pytest": lambda patterns, *_args: _materialize_flag_pairs(patterns, "--ignore"),
    "codespell": _materialize_codespell,
    "yamllint": _materialize_yamllint,
    "yamlfmt": _materialize_yamlfmt,
    "jscpd": _materialize_jscpd,
}
