"""Packaging: bundled catalog must load from the installable package."""

from __future__ import annotations

import glob
import subprocess
import zipfile
from pathlib import Path

import pytest

from shipgate.registry import BUNDLE_ROOT, Registry


def test_bundle_root_exists_and_loads_catalog() -> None:
    assert (BUNDLE_ROOT / "catalog" / "tools").is_dir()
    assert (BUNDLE_ROOT / "defaults").is_dir()
    assert (BUNDLE_ROOT / "suites").is_dir()
    registry = Registry()
    assert len(registry.tools) >= 20
    assert "ruff" in registry.tools
    assert len(registry.checks) >= 20
    assert len(registry.suites) >= 1


@pytest.mark.integration
def test_wheel_contains_bundle() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["uv", "build"], cwd=root, check=True, capture_output=True)
    wheels = sorted(glob.glob(str(root / "dist" / "*.whl")))
    assert wheels, "uv build produced no wheel"
    with zipfile.ZipFile(wheels[-1]) as archive:
        names = archive.namelist()
    assert any(name.endswith("bundle/catalog/tools/ruff.yaml") for name in names)
    assert any("/bundle/defaults/" in name for name in names)
