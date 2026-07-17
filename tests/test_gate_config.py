from __future__ import annotations

from pathlib import Path

from shipgate.gate_config import gate_env_from_config, load_gate_config, resolve_gate_config_path
from shipgate.registry import BUNDLE_ROOT, Registry


def test_bundled_gate_config_loads(tmp_path: Path) -> None:
    check = Registry().get_check("gate.module-size")
    _, config = load_gate_config(check, tmp_path, None)
    assert config["portfolio_max_lines"] == 1000
    assert "src/" in config["scan_roots"]


def test_gate_env_flattens_lists() -> None:
    env = gate_env_from_config({"scan_roots": ["src/", "docs/"]}, Path("."))
    assert env["GATE_SCAN_ROOTS"] == "src/ docs/"


def test_bundled_script_path_convention() -> None:
    script = BUNDLE_ROOT / "defaults" / "gates" / "module-size.sh"
    assert script.exists()


def test_resolve_project_override(tmp_path: Path) -> None:
    check = Registry().get_check("gate.module-size")
    config_dir = tmp_path / ".shipgate" / "configs" / "gates"
    config_dir.mkdir(parents=True)
    (config_dir / "gate.module-size.yaml").write_text(
        "portfolio_max_lines: 42\nscan_roots:\n  - custom/\n",
        encoding="utf-8",
    )
    path = resolve_gate_config_path(check, tmp_path, None)
    assert path is not None
    assert path.name == "gate.module-size.yaml"
    _, data = load_gate_config(check, tmp_path, None)
    assert data["portfolio_max_lines"] == 42


def test_gate_check_declares_config() -> None:
    check = Registry().get_check("gate.module-size")
    assert check.config is not None
    assert check.config.bundled == "gates/module-size.yaml"
    assert check.config.allowlist_bundled == "module-size.txt"
