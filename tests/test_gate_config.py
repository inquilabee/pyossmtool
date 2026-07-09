from __future__ import annotations

from pathlib import Path

from pyaitools.gate_config import gate_env_from_config, load_gate_config, resolve_gate_config_path
from pyaitools.registry import PACKAGE_ROOT


def test_bundled_gate_config_loads(tmp_path: Path) -> None:
    _, config = load_gate_config("gate.module-size", tmp_path, None)
    assert config["portfolio_max_lines"] == 1000
    assert "src/" in config["scan_roots"]


def test_gate_env_flattens_lists() -> None:
    env = gate_env_from_config({"scan_roots": ["src/", "docs/"]}, Path("."))
    assert env["GATE_SCAN_ROOTS"] == "src/ docs/"


def test_bundled_script_path_convention() -> None:
    script = PACKAGE_ROOT / "defaults" / "gates" / "module-size.sh"
    assert script.exists()


def test_resolve_project_override(tmp_path: Path) -> None:
    config_dir = tmp_path / ".pyaitools" / "configs" / "gates"
    config_dir.mkdir(parents=True)
    (config_dir / "gate.module-size.yaml").write_text(
        "portfolio_max_lines: 42\nscan_roots:\n  - custom/\n",
        encoding="utf-8",
    )
    path = resolve_gate_config_path("gate.module-size", tmp_path, None)
    assert path.name == "gate.module-size.yaml"
    _, data = load_gate_config("gate.module-size", tmp_path, None)
    assert data["portfolio_max_lines"] == 42
