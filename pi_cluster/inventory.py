"""Render the Ansible inventory from the cluster config.

Groups:
    control_plane   the single control-plane node
    workers         every other node
    storage         the node with the SSD (empty if there is none)
"""

from __future__ import annotations

from pathlib import Path

from pi_cluster.config import ClusterConfig, config_dir

INVENTORY_FILENAME = "inventory.ini"


def inventory_path() -> Path:
    return config_dir() / INVENTORY_FILENAME


def _host(node) -> str:
    return f"{node.name} ansible_host={node.address}"


def render_inventory(config: ClusterConfig) -> str:
    config.validate()
    cp = config.control_plane
    assert cp is not None  # guaranteed by validate()

    lines = ["[control_plane]", _host(cp), "", "[workers]"]
    lines += [_host(n) for n in config.workers]

    lines += ["", "[storage]"]
    storage = config.storage_node()
    if storage is not None:
        lines.append(_host(storage))

    key = Path(config.ssh.private_key).expanduser()
    lines += [
        "",
        "[all:vars]",
        f"ansible_user={config.ssh.username}",
        f"ansible_ssh_private_key_file={key}",
        "ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'",
        "ansible_python_interpreter=auto_silent",
        f"storage_device={config.storage.device}",
        f"storage_mount={config.storage.mount}",
        f"storage_fstype={config.storage.fstype}",
    ]
    return "\n".join(lines) + "\n"


def write_inventory(config: ClusterConfig) -> Path:
    path = inventory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_inventory(config))
    return path
