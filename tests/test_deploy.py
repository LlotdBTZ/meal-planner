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
        schedule = _unit(timer)["Timer"]
        assert "OnCalendar" in schedule or "OnUnitActiveSec" in schedule, timer.name


def test_app_service_is_memory_capped_and_restarts():
    service = _unit(DEPLOY / "meal-planner.service")["Service"]
    assert service["MemoryMax"] == "300M"
    assert service["Restart"] == "on-failure"
    assert service["User"] == "mealplanner"
    assert service["ExecStart"].endswith("-m app.main")


def test_autodeploy_runs_the_deployed_script_against_the_checkout():
    service = _unit(DEPLOY / "meal-planner-autodeploy.service")
    # The tagged, root-owned copy runs, never the checkout's working tree.
    assert service["Service"]["ExecStart"] == "/opt/meal-planner/current/deploy/update.sh --auto"
    assert service["Service"]["Environment"] == "MEAL_PLANNER_REPO=@REPO@"
    assert "s|@REPO@|$REPO|g" in (DEPLOY / "install.sh").read_text()


def test_only_the_autodeploy_unit_has_a_placeholder():
    for unit in UNIT_FILES:
        if unit.name != "meal-planner-autodeploy.service":
            assert "@" not in unit.read_text(), unit.name


def test_install_warns_when_memory_limits_cannot_work():
    text = (DEPLOY / "install.sh").read_text()
    assert "/sys/fs/cgroup/cgroup.controllers" in text
    assert "cgroup_enable=memory" in text
