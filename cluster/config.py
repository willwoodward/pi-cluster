"""Load and save ``cluster-config.json`` — the single source of truth for a cluster.

The config is intentionally small and human-editable. ``cluster init`` writes it
after discovery; every other command reads it (and regenerates ``inventory.ini``
from it, so the two never drift).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

CONFIG_FILENAME = "cluster-config.json"
DEFAULT_HOSTNAME_PREFIX = "pi-node"
DEFAULT_USERNAME = "pi"
DEFAULT_KEY_PATH = "~/.ssh/pi-cluster"
DEFAULT_STORAGE_MOUNT = "/mnt/ssd"

CONTROL_PLANE = "control-plane"
WORKER = "worker"


@dataclass
class Node:
    """A single Raspberry Pi in the cluster."""

    name: str  # hostname, e.g. "pi-node-01"
    address: str  # how Ansible reaches it: "pi-node-01.local" or an IP
    role: str = WORKER  # CONTROL_PLANE or WORKER

    @property
    def is_control_plane(self) -> bool:
        return self.role == CONTROL_PLANE


@dataclass
class SSHConfig:
    username: str = DEFAULT_USERNAME
    private_key: str = DEFAULT_KEY_PATH
    hostname_prefix: str = DEFAULT_HOSTNAME_PREFIX


@dataclass
class StorageConfig:
    """The node with the SSD attached, exported over NFS (used by the registry)."""

    node: Optional[str] = None  # node name that has the SSD; defaults to control-plane
    device: str = "/dev/sda1"
    mount: str = DEFAULT_STORAGE_MOUNT


@dataclass
class ClusterConfig:
    ssh: SSHConfig = field(default_factory=SSHConfig)
    nodes: List[Node] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mode: Optional[str] = None  # last mode applied, e.g. "kubernetes"

    # ---- convenience -----------------------------------------------------
    @property
    def control_plane(self) -> Optional[Node]:
        return next((n for n in self.nodes if n.is_control_plane), None)

    @property
    def workers(self) -> List[Node]:
        return [n for n in self.nodes if not n.is_control_plane]

    def storage_node(self) -> Optional[Node]:
        """Resolve the node that hosts the SSD (defaults to the control-plane)."""
        target = self.storage.node or (self.control_plane.name if self.control_plane else None)
        return next((n for n in self.nodes if n.name == target), None)

    # ---- (de)serialisation ----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "ssh": asdict(self.ssh),
            "nodes": [asdict(n) for n in self.nodes],
            "storage": asdict(self.storage),
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClusterConfig":
        return cls(
            ssh=SSHConfig(**data.get("ssh", {})),
            nodes=[Node(**n) for n in data.get("nodes", [])],
            storage=StorageConfig(**data.get("storage", {})),
            mode=data.get("mode"),
        )


def config_path(directory: Optional[Path] = None) -> Path:
    return (directory or Path.cwd()) / CONFIG_FILENAME


def load_config(directory: Optional[Path] = None) -> ClusterConfig:
    path = config_path(directory)
    if not path.exists():
        raise FileNotFoundError(
            f"No {CONFIG_FILENAME} found in {path.parent}. Run `cluster init` first."
        )
    with path.open() as fh:
        return ClusterConfig.from_dict(json.load(fh))


def save_config(config: ClusterConfig, directory: Optional[Path] = None) -> Path:
    path = config_path(directory)
    with path.open("w") as fh:
        json.dump(config.to_dict(), fh, indent=4)
        fh.write("\n")
    return path
