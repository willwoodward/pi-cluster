"""Locate bundled playbooks and run them with ansible-playbook."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

from pi_cluster.inventory import inventory_path


def data_path(*parts: str) -> Path:
    """Resolve a path inside the packaged ``pi_cluster/data`` tree."""
    base = resources.files("pi_cluster") / "data"
    for part in parts:  # joinpath() only takes one argument before Python 3.11
        base = base / part
    return Path(str(base))


def _ansible_playbook() -> str:
    exe = shutil.which("ansible-playbook")
    if exe is None:
        raise RuntimeError(
            "ansible-playbook not found on PATH. It ships with pi-cluster's "
            "ansible-core dependency; if you used pipx, make sure ~/.local/bin is on PATH."
        )
    return exe


def build_command(
    playbook: Path, inventory: Path, vars_file: Path, limit: list[str] | None = None
) -> list[str]:
    cmd = [_ansible_playbook(), "-i", str(inventory), "-e", f"@{vars_file}", str(playbook)]
    if limit:
        cmd += ["--limit", ",".join(limit)]
    return cmd


def run_playbook(
    playbook: str, extra_vars: dict | None = None, limit: list[str] | None = None
) -> None:
    """Run a bundled playbook (path relative to ``data/``) against the cluster.

    Extra vars go through a JSON file, so values with spaces or quotes survive.
    ``pi_cluster_data`` is always set, so playbooks can reference shared files.
    """
    path = data_path(playbook)
    if not path.exists():
        raise FileNotFoundError(f"Bundled playbook missing: {path}")
    inventory = inventory_path()
    if not inventory.exists():
        raise FileNotFoundError(f"No inventory at {inventory}. Run `cluster init` first.")

    variables = {"pi_cluster_data": str(data_path())}
    variables.update(extra_vars or {})

    env = dict(os.environ)
    env.setdefault("ANSIBLE_RETRY_FILES_ENABLED", "False")
    env.setdefault("ANSIBLE_DEPRECATION_WARNINGS", "False")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(variables, fh)
        vars_file = Path(fh.name)
    try:
        result = subprocess.run(build_command(path, inventory, vars_file, limit), env=env)
    finally:
        vars_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"{playbook} failed (exit code {result.returncode}).")
