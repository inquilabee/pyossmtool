"""Integration: wheel install exposes catalog and CLI."""

from __future__ import annotations

import glob
import subprocess
import venv
from pathlib import Path

import pytest


@pytest.mark.integration
def test_wheel_install_lists_tools_and_runs_check(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["uv", "build"], cwd=root, check=True, capture_output=True)
    wheels = sorted(glob.glob(str(root / "dist" / "shipgate-*.whl")))
    assert wheels, "uv build produced no shipgate wheel"
    wheel = wheels[-1]

    venv_dir = tmp_path / "venv"
    venv.create(venv_dir, with_pip=True)
    pip = venv_dir / "bin" / "pip"
    shipgate = venv_dir / "bin" / "shipgate"
    subprocess.run([str(pip), "install", wheel], check=True, capture_output=True)

    listed = subprocess.run(
        [str(shipgate), "list", "tools"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ruff" in listed.stdout

    (tmp_path / "shipgate.yaml").write_text(
        "suite: formatting\nenv: managed\ntarget: .\nconfigs:\n  mode: auto\n",
        encoding="utf-8",
    )
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = subprocess.run(
        [str(shipgate), "check", "--suite", "formatting"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "Unknown check:" not in combined
    assert "Unknown tool:" not in combined
    assert "Traceback" not in combined
