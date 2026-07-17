"""Tests for unified ignore-profile and ignore-path handling."""

from __future__ import annotations

from pathlib import Path

import yaml

from shipgate.ignore import (
    BUNDLED_IGNORE_PATHS,
    EffectiveIgnores,
    filter_findings,
    materialize_for_tool,
    merge_ignore_specs,
    resolve_effective_ignores,
)
from shipgate.models import (
    CheckDef,
    Finding,
    IgnoreSpec,
    Location,
    ProjectConfig,
    Severity,
    SuiteCheckRef,
    SuiteDef,
)
from shipgate.registry import Registry


def test_merge_ignore_specs_unions_layers() -> None:
    merged = merge_ignore_specs(
        IgnoreSpec(ignore_profile=[".gitignore"], ignore_paths=["venv/"]),
        IgnoreSpec(ignore_paths=["reports/", "venv/"]),
        IgnoreSpec(ignore_profile=[".cursorignore"]),
    )
    assert merged.ignore_profile == [".gitignore", ".cursorignore"]
    assert merged.ignore_paths == ["venv/", "reports/"]


def test_resolve_effective_ignores_reads_profiles(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
    suite = SuiteDef(
        id="demo",
        name="Demo",
        description="demo",
        checks=[],
        ignore_profile=[".gitignore"],
        ignore_paths=[".shipgate/"],
    )
    project = ProjectConfig(suite="demo", ignore_paths=["tmp/"])
    check = CheckDef(
        id="ruff.lint",
        tool="ruff",
        name="Ruff",
        description="lint",
        parser="ruff_json",
        ignore_paths=["**/generated/**"],
    )
    check_ref = SuiteCheckRef(id="ruff.lint", ignore_paths=["scratch/"])

    ignores = resolve_effective_ignores(
        tmp_path,
        suite=suite,
        project_config=project,
        check_ref=check_ref,
        check=check,
    )

    assert ignores.is_ignored("build/output.txt")
    assert ignores.is_ignored(".shipgate/cache/foo")
    assert ignores.is_ignored("tmp/file.txt")
    assert ignores.is_ignored("scratch/note.txt")
    assert not ignores.is_ignored("src/app.py")


def test_filter_findings_drops_ignored_locations() -> None:
    ignores = EffectiveIgnores(path_patterns=["reports/"])
    findings = [
        Finding(
            rule_id="demo",
            severity=Severity.ERROR,
            message="bad",
            location=Location(file="reports/fail.json"),
        ),
        Finding(
            rule_id="demo",
            severity=Severity.ERROR,
            message="good",
            location=Location(file="src/app.py"),
        ),
    ]
    filtered = filter_findings(findings, ignores)
    assert len(filtered) == 1
    assert filtered[0].location
    assert filtered[0].location.file == "src/app.py"


def test_materialize_yamllint_merges_base_config(tmp_path: Path) -> None:
    base = tmp_path / "yamllint.yaml"
    base.write_text(
        yaml.safe_dump({"extends": "default", "rules": {"line-length": {"max": 120}}}),
        encoding="utf-8",
    )
    ignores = EffectiveIgnores(path_patterns=["venv/", "reports/"])
    material = materialize_for_tool(
        Registry().get_tool("yamllint"),
        ignores,
        project_root=tmp_path,
        check_id="yamllint.check",
        base_config_path=base,
    )
    assert material.config_path
    payload = yaml.safe_load(material.config_path.read_text(encoding="utf-8"))
    assert "venv/" in payload["ignore"]
    assert "reports/" in payload["ignore"]
    assert payload["rules"]["line-length"]["max"] == 120


def test_materialize_yamlfmt_merges_exclude(tmp_path: Path) -> None:
    base = tmp_path / "yamlfmt.yaml"
    base.write_text(
        yaml.safe_dump({"formatter": {"type": "basic"}, "exclude": ["node_modules/"]}),
        encoding="utf-8",
    )
    ignores = EffectiveIgnores(path_patterns=["venv/"])
    material = materialize_for_tool(
        Registry().get_tool("yamlfmt"),
        ignores,
        project_root=tmp_path,
        check_id="yamlfmt.format",
        base_config_path=base,
    )
    assert material.config_path
    payload = yaml.safe_load(material.config_path.read_text(encoding="utf-8"))
    assert payload["exclude"] == ["node_modules/", "venv/"]


def test_registry_loads_suite_ignore_fields() -> None:
    registry = Registry()
    suite = registry.get_suite("reslab-parity")
    assert ".gitignore" in suite.ignore_profile
    assert ".shipgate/" in suite.ignore_paths


def test_tool_ignore_declared_on_catalog() -> None:
    ruff = Registry().get_tool("ruff")
    assert ruff.ignore is not None
    assert ruff.ignore.kind.value == "config_overlay"
    bandit = Registry().get_tool("bandit")
    assert bandit.ignore is not None
    assert bandit.ignore.flag == "-x"


def test_bundled_ignore_paths_exclude_venv_and_reports(tmp_path: Path) -> None:
    ignores = resolve_effective_ignores(tmp_path, suite=Registry().get_suite("python-quality"))
    for pattern in (".venv/lib/foo.py", "reports/fail.json", ".shipgate/tools/bin/ruff"):
        assert ignores.is_ignored(pattern)
    assert not ignores.is_ignored("src/app.py")


def test_bundled_ignore_paths_constant_is_applied_globally(tmp_path: Path) -> None:
    ignores = resolve_effective_ignores(tmp_path)
    for path in BUNDLED_IGNORE_PATHS:
        sample = f"{path.rstrip('/')}/example.txt"
        assert ignores.is_ignored(sample), path


def test_materialize_ty_skips_gitignore_only_patterns(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(
        "*$py.class\n*.py,cover\n**_cache**\nbuild/\n",
        encoding="utf-8",
    )
    ignores = resolve_effective_ignores(tmp_path, suite=Registry().get_suite("standard"))
    material = materialize_for_tool(
        Registry().get_tool("ty"),
        ignores,
        project_root=tmp_path,
        check_id="ty.check",
    )
    assert material.argv
    joined = " ".join(material.argv)
    assert "*$py.class" not in joined
    assert "*.py,cover" not in joined
    assert "**_cache**" not in joined
    assert "--exclude" in joined
    assert "build/" in joined
