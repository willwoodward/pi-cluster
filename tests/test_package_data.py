"""The bundled playbooks exist, parse, and pass `ansible-playbook --syntax-check`."""

import shutil
import subprocess

import pytest

from pi_cluster.ansible_runner import data_path
from pi_cluster.modes import MODES

yaml = pytest.importorskip("yaml")  # ships with ansible-core

ENTRY_PLAYBOOKS = sorted(
    {
        pb
        for m in MODES.values()
        for pb in m.create_playbooks + m.demo_playbooks + m.destroy_playbooks
    }
    | {
        "playbooks/base-setup.yml",
        "playbooks/shutdown.yml",
        "playbooks/reset.yml",
        "lights/install.yml",
        "services/deploy.yml",
        "services/remove.yml",
    }
)


@pytest.mark.parametrize("playbook", ENTRY_PLAYBOOKS)
def test_playbook_exists(playbook):
    assert data_path(playbook).is_file()


def test_every_yaml_file_parses():
    files = [p for p in data_path().rglob("*.yml")]
    assert files
    for path in files:
        list(yaml.safe_load_all(path.read_text()))


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")
@pytest.mark.parametrize("playbook", ENTRY_PLAYBOOKS)
def test_syntax_check(playbook, tmp_path):
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[control_plane]\na\n[workers]\nb\n[storage]\na\n")
    result = subprocess.run(
        [
            "ansible-playbook",
            "--syntax-check",
            "-i",
            str(inventory),
            "-e",
            f"pi_cluster_data={data_path()}",
            str(data_path(playbook)),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
