"""The cluster config: which Pis exist, how to reach them, and what is running.

It lives in ``~/.config/pi-cluster/config.json`` (override the directory with
``$PI_CLUSTER_HOME``), so every ``cluster`` command works from any folder —
including your own project repos. ``inventory.ini`` is regenerated next to it
on every command, so the two never drift.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_FILENAME = "config.json"
LEGACY_CONFIG_FILENAME = "cluster-config.json"  # pre-0.1 location, in the cwd

DEFAULT_HOSTNAME_PREFIX = "pi-node"
DEFAULT_USERNAME = "pi"
DEFAULT_KEY_PATH = "~/.ssh/pi-cluster"
DEFAULT_STORAGE_DEVICE = "/dev/sda1"
DEFAULT_STORAGE_MOUNT = "/mnt/ssd"

CONTROL_PLANE = "control-plane"
WORKER = "worker"
ROLES = (CONTROL_PLANE, WORKER)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def config_dir() -> Path:
    """Directory holding config.json and inventory.ini."""
    override = os.environ.get("PI_CLUSTER_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "pi-cluster"


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


@dataclass
class Node:
    """A single Raspberry Pi in the cluster."""

    name: str  # hostname, e.g. "pi-node-01"
    address: str  # how we reach it: "pi-node-01.local" or an IP
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
    """Optional SSD exported over NFS (backs the kubernetes registry).

    ``node = None`` means no SSD: the registry falls back to local storage.
    """

    node: str | None = None
    device: str = DEFAULT_STORAGE_DEVICE
    mount: str = DEFAULT_STORAGE_MOUNT
    fstype: str = "ext4"


@dataclass
class ClusterConfig:
    ssh: SSHConfig = field(default_factory=SSHConfig)
    nodes: list[Node] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    mode: str | None = None  # the active mode, e.g. "kubernetes"; None = bare

    # ---- lookups ---------------------------------------------------------
    @property
    def control_plane(self) -> Node | None:
        return next((n for n in self.nodes if n.is_control_plane), None)

    @property
    def workers(self) -> list[Node]:
        return [n for n in self.nodes if not n.is_control_plane]

    def storage_node(self) -> Node | None:
        if not self.storage.node:
            return None
        return self.node(self.storage.node)

    def node(self, name: str) -> Node | None:
        return next((n for n in self.nodes if n.name == name), None)

    def find_node(self, ref: str) -> Node:
        """Find a node by exact name, or by number (``2`` -> ``pi-node-02``)."""
        exact = self.node(ref)
        if exact:
            return exact
        if ref.isdigit():
            suffix = f"-{int(ref):02d}"
            matches = [n for n in self.nodes if n.name.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
        names = ", ".join(n.name for n in self.nodes) or "(none)"
        raise ValueError(f"No node called '{ref}'. Nodes: {names}.")

    # ---- validation ------------------------------------------------------
    def validate(self) -> None:
        """Raise ValueError if the config can't be used to drive the cluster."""
        if not self.nodes:
            raise ValueError(
                f"No nodes in {config_path()}. Run `cluster init`, or add them by hand."
            )
        seen = set()
        for n in self.nodes:
            if not _NAME_RE.match(n.name):
                raise ValueError(f"Invalid node name '{n.name}'.")
            if n.name in seen:
                raise ValueError(f"Node '{n.name}' is listed twice.")
            seen.add(n.name)
            if n.role not in ROLES:
                raise ValueError(
                    f"Node '{n.name}' has role '{n.role}'; expected one of {', '.join(ROLES)}."
                )
        control_planes = [n for n in self.nodes if n.is_control_plane]
        if len(control_planes) != 1:
            raise ValueError(
                f"Exactly one node needs role '{CONTROL_PLANE}' (found {len(control_planes)})."
            )
        if self.storage.node and not self.node(self.storage.node):
            raise ValueError(f"storage.node '{self.storage.node}' is not one of the nodes.")

    # ---- (de)serialisation ----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "ssh": asdict(self.ssh),
            "nodes": [asdict(n) for n in self.nodes],
            "storage": asdict(self.storage),
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ClusterConfig:
        try:
            return cls(
                ssh=SSHConfig(**data.get("ssh", {})),
                nodes=[Node(**n) for n in data.get("nodes", [])],
                storage=StorageConfig(**data.get("storage", {})),
                mode=data.get("mode"),
            )
        except TypeError as exc:  # unknown / missing keys
            raise ValueError(f"Invalid cluster config: {exc}") from None


def _migrate_legacy() -> bool:
    """Copy ./cluster-config.json into the config dir if that's all we have."""
    legacy = Path.cwd() / LEGACY_CONFIG_FILENAME
    target = config_path()
    if target.exists() or not legacy.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(legacy, target)
    print(f"Copied {legacy} to {target} (the config now lives there; you can delete the old file).")
    return True


def config_exists() -> bool:
    return config_path().exists() or (Path.cwd() / LEGACY_CONFIG_FILENAME).exists()


def load_config() -> ClusterConfig:
    _migrate_legacy()
    path = config_path()
    if not path.exists():
        raise FileNotFoundError(f"No cluster config at {path}. Run `cluster init` first.")
    try:
        with path.open() as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from None
    return ClusterConfig.from_dict(data)


def save_config(config: ClusterConfig) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as fh:
        json.dump(config.to_dict(), fh, indent=4)
        fh.write("\n")
    tmp.replace(path)
    return path
