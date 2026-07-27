"""Locate bundled playbooks and run them with ansible-playbook."""

from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import List, Optional


def data_path(*parts: str) -> Path:
    """Resolve a path inside the packaged ``cluster/data`` tree."""
    base = resources.files("cluster") / "data"
    for part in parts:
        base = base / part
    return Path(str(base))


def _ensure_ansible() -> None:
    if shutil.which("ansible-playbook") is None:
        raise RuntimeError(
            "ansible-playbook not found on PATH. Install it with "
            "`pip install ansible-core` (or `pipx inject pi-cluster ansible-core`)."
        )


def run_playbook(
    playbook: Path,
    inventory: Path,
    extra_vars: Optional[dict] = None,
    check: bool = True,
) -> int:
    """Run a playbook against the given inventory. Returns the exit code."""
    _ensure_ansible()
    if not playbook.exists():
        raise FileNotFoundError(f"Playbook not found: {playbook}")
    if not inventory.exists():
        raise FileNotFoundError(
            f"Inventory not found: {inventory}. Run `cluster init` first."
        )

    cmd: List[str] = ["ansible-playbook", "-i", str(inventory), str(playbook)]
    if extra_vars:
        for key, value in extra_vars.items():
            cmd += ["-e", f"{key}={value}"]

    result = subprocess.run(cmd)
    if check and result.returncode != 0:
        raise RuntimeError(f"Playbook failed ({playbook.name}), exit code {result.returncode}.")
    return result.returncode
