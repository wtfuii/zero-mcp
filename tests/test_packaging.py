"""Packaging invariants required by the release pipeline."""

import tomllib
from importlib.metadata import entry_points, version
from pathlib import Path

from zero_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_metadata_matches_runtime_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "finanzen-zero-mcp"
    assert project["version"] == __version__
    assert version("finanzen-zero-mcp") == __version__


def test_wheel_builds_the_zero_mcp_package() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["uv"]["build-backend"]["module-name"] == "zero_mcp"


def test_console_script_is_stable() -> None:
    scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}

    assert scripts["zero-mcp"] == "zero_mcp.__main__:main"
