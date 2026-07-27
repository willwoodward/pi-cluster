"""Registry of cluster *modes* — the pluggable distributed-systems environments.

Today there is one mode, ``kubernetes``. The structure is deliberately open so
future modes (a Raft demo, MPI, a gossip protocol, ...) can drop in as a new
folder under ``cluster/data/modes/<name>`` plus an entry here, and reuse the
same discovery, inventory, and LED-visualiser machinery.

Each mode lists the playbooks to run, in order, for ``create`` and ``destroy``.
Paths are relative to ``cluster/data/modes/<name>/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Mode:
    name: str
    summary: str
    create_playbooks: List[str] = field(default_factory=list)
    deploy_playbooks: List[str] = field(default_factory=list)
    destroy_playbooks: List[str] = field(default_factory=list)


MODES: Dict[str, Mode] = {
    "kubernetes": Mode(
        name="kubernetes",
        summary="k3s cluster with a private registry, example apps, and an optional LED pod-visualiser.",
        create_playbooks=[
            "install.yml",          # install k3s across control-plane + workers
            "setup-nfs.yml",        # export the SSD over NFS from the storage node
            "configure-registry.yml",  # point k3s at the in-cluster registry mirror
            "deploy.yml",           # apply the registry + example manifests
        ],
        deploy_playbooks=[
            "copy-lights.yml",      # install the LED serial script on every node
            "deploy-apps.yml",      # build + push images, then roll out operator + Flask
        ],
        destroy_playbooks=["uninstall.yml"],
    ),
}


def get_mode(name: str) -> Mode:
    try:
        return MODES[name]
    except KeyError:
        available = ", ".join(sorted(MODES))
        raise KeyError(f"Unknown mode '{name}'. Available modes: {available}.")
