"""Registry of cluster *modes* — whole environments layered on top of bare nodes.

Only one mode is active at a time. ``destroy`` takes the nodes back to bare,
and ``cluster reset`` gets there from any state.

Every mode gets a command group named after it (plus any aliases) with the same
lifecycle verbs — ``cluster <mode> up | down | demo`` — and can add its own
commands through ``commands``, a module with a ``register(subparsers)``
function (see :mod:`pi_cluster.kube`).

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
    aliases: tuple[str, ...] = ()  # shorter names for `cluster <mode> ...`
    commands: str | None = None  # module adding mode-specific commands
    create_playbooks: list[str] = field(default_factory=list)
    demo_playbooks: list[str] = field(default_factory=list)  # optional extras
    demo_images: dict[str, str] = field(default_factory=dict)  # name -> build folder in data/
    destroy_playbooks: list[str] = field(default_factory=list)
    next_steps: str = ""


MODES: dict[str, Mode] = {
    "kubernetes": Mode(
        name="kubernetes",
        summary="k3s with a private registry and an nginx example.",
        aliases=("kube", "k3s"),
        commands="pi_cluster.kube",
        create_playbooks=[
            "modes/kubernetes/install.yml",  # registry mirror config + k3s server/agents
            "modes/kubernetes/storage.yml",  # mount the SSD and export it over NFS
            "modes/kubernetes/registry.yml",  # in-cluster registry + nginx example
        ],
        demo_playbooks=[
            "lights/install.yml",  # cluster-led on every node
            "modes/kubernetes/demo.yml",  # build + roll out LED operator and Flask app
        ],
        demo_images={
            "pod-operator": "modes/kubernetes/manifests/pod-operator/app",
            "demo-flask": "modes/kubernetes/manifests/example-flask-api/app",
        },
        destroy_playbooks=["modes/kubernetes/uninstall.yml"],
        next_steps="Run `cluster kube config` to use kubectl from this machine.",
    ),
}


def get_mode(name: str) -> Mode:
    for mode in MODES.values():
        if name in (mode.name, *mode.aliases):
            return mode
    available = ", ".join(sorted(MODES))
    raise ValueError(f"Unknown mode '{name}'. Available modes: {available}.")
