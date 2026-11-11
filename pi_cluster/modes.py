"""Registry of cluster *modes* — whole environments layered on top of bare nodes.

Only one mode is active at a time. ``destroy`` takes the nodes back to bare,
and ``cluster reset`` gets there from any state.

Adding a mode: create ``pi_cluster/data/modes/<name>/`` with its playbooks and
add an entry below. Playbook paths are relative to ``pi_cluster/data/``. Use
``tasks/apt-install.yml`` (with ``component: <name>``) for packages, so destroy
and reset can remove exactly what the mode installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mode:
    name: str
    summary: str
    create_playbooks: list[str] = field(default_factory=list)
    demo_playbooks: list[str] = field(default_factory=list)  # optional extras
    destroy_playbooks: list[str] = field(default_factory=list)
    next_steps: str = ""


MODES: dict[str, Mode] = {
    "kubernetes": Mode(
        name="kubernetes",
        summary="k3s with a private registry and an nginx example.",
        create_playbooks=[
            "modes/kubernetes/install.yml",  # registry mirror config + k3s server/agents
            "modes/kubernetes/storage.yml",  # mount the SSD and export it over NFS
            "modes/kubernetes/registry.yml",  # in-cluster registry + nginx example
        ],
        demo_playbooks=[
            "lights/install.yml",  # cluster-led on every node
            "modes/kubernetes/demo.yml",  # build + roll out LED operator and Flask app
        ],
        destroy_playbooks=["modes/kubernetes/uninstall.yml"],
        next_steps="Run `cluster kubeconfig` to use kubectl from this machine.",
    ),
}


def get_mode(name: str) -> Mode:
    try:
        return MODES[name]
    except KeyError:
        available = ", ".join(sorted(MODES))
        raise ValueError(f"Unknown mode '{name}'. Available modes: {available}.") from None
