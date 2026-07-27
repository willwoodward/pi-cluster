"""Generate ``inventory.ini`` from ``cluster-config.json``.

The inventory is regenerated from the config on every command, so the Ansible
inventory always reflects the recorded cluster.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cluster.config import ClusterConfig

INVENTORY_FILENAME = "inventory.ini"


def render_inventory(config: ClusterConfig) -> str:
    cp = config.control_plane
    if cp is None:
        raise ValueError("Cluster config has no control-plane node.")

    lines = ["[master]"]
    lines.append(f"{cp.name} ansible_host={cp.address}")

    lines.append("")
    lines.append("[workers]")
    for node in config.workers:
        lines.append(f"{node.name} ansible_host={node.address}")

    storage = config.storage_node()
    lines.append("")
    lines.append("[storage]")
    if storage is not None:
        lines.append(f"{storage.name} ansible_host={storage.address}")

    lines.append("")
    lines.append("[all:vars]")
    lines.append(f"ansible_user={config.ssh.username}")
    lines.append(f"ansible_ssh_private_key_file={config.ssh.private_key}")
    lines.append("ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'")
    lines.append(f"storage_mount={config.storage.mount}")
    lines.append(f"storage_device={config.storage.device}")
    lines.append(f"control_plane_host={cp.address}")

    return "\n".join(lines) + "\n"


def write_inventory(config: ClusterConfig, directory: Optional[Path] = None) -> Path:
    path = (directory or Path.cwd()) / INVENTORY_FILENAME
    path.write_text(render_inventory(config))
    return path
