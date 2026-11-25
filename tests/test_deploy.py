"""Sanity checks for deploy/: scripts parse, units match what install.sh installs."""

import configparser
import os
import re
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
SCRIPTS = sorted(DEPLOY.glob("*.sh"))
UNIT_FILES = sorted(p for p in DEPLOY.iterdir() if p.suffix in {".service", ".timer"})


def _unit(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(path.read_text())
    return parser


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_are_valid_bash_and_executable(script):
    subprocess.run(["bash", "-n", str(script)], check=True)
    assert os.access(script, os.X_OK), f"{script.name} is not executable"


def test_install_installs_every_unit_in_deploy():
    text = (DEPLOY / "install.sh").read_text()
    listed = re.search(r"UNITS=\((.*?)\)", text, re.S).group(1).split()
    assert sorted(listed) == [p.name for p in UNIT_FILES]


def test_every_timer_has_a_service():
    for timer in DEPLOY.glob("*.timer"):
        assert timer.with_suffix(".service").is_file(), timer.name
        assert "OnCalendar" in _unit(timer)["Timer"]


def test_app_service_is_memory_capped_and_restarts():
    service = _unit(DEPLOY / "meal-planner.service")["Service"]
    assert service["MemoryMax"] == "300M"
    assert service["Restart"] == "on-failure"
    assert service["User"] == "mealplanner"
    assert service["ExecStart"].endswith("-m app.main")
