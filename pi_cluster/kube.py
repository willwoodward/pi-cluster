"""The ``kubernetes`` mode's own commands (``cluster kubernetes …``) and app support.

Two ways to use k3s:

- **kubectl** (for learning): ``cluster kubernetes config`` sets kubectl up,
  ``cluster kubernetes build`` turns a Dockerfile into an image you can use in
  your own YAML, and ``cluster kubernetes registry`` shows what's stored.
- **cluster.toml** ``[apps]`` (no kubectl needed): ``cluster deploy`` builds
  the images, generates the Deployment and Service, and rolls them out.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

from pi_cluster import images, remote
from pi_cluster import project as proj
from pi_cluster.ansible_runner import run_playbook
from pi_cluster.cliutil import CLIError, load_cluster, require_mode
from pi_cluster.config import ClusterConfig

MODE = "kubernetes"
KUBECONFIG_DEFAULT = "~/.kube/pi-cluster.yaml"


def kubectl(config: ClusterConfig, args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run kubectl on the control-plane (no kubectl needed on this machine)."""
    cp = config.control_plane
    assert cp is not None
    return remote.run(config, cp, f"sudo -n k3s kubectl {args}", timeout=timeout)


def build_images(builds: list[images.ImageBuild], force: bool = False) -> None:
    """Pack the build folders, then build and push them on the control-plane."""
    with tempfile.TemporaryDirectory(prefix="pi-cluster-build-") as tmp:
        run_playbook("apps/build.yml", extra_vars=images.build_vars(builds, Path(tmp), force))


# --------------------------------------------------------------------------- #
# cluster.toml [apps]
# --------------------------------------------------------------------------- #
def deploy_apps(config: ClusterConfig, apps: list[proj.App]) -> None:
    require_mode(config, MODE)
    builds = {a.name: images.plan(a.name, a.build) for a in apps if a.build}
    if builds:
        print("Building images on the control-plane ...")
        build_images(list(builds.values()))
    payload = []
    for app in apps:
        image = builds[app.name].ref if app.name in builds else app.image
        assert image is not None
        print(f"  {app.name:<16} {image}  x{app.replicas}")
        payload.append(
            {
                "name": app.name,
                "manifest": proj.app_manifest(app, image),
                "has_service": app.port is not None,
            }
        )
    run_playbook("apps/apply.yml", extra_vars={"apps": payload})


def remove_apps(config: ClusterConfig, names: list[str]) -> None:
    if config.mode != MODE:
        return  # no k3s, so no apps to remove
    run_playbook("apps/remove.yml", extra_vars={"app_names": names})


def app_names_on_cluster(config: ClusterConfig) -> list[str]:
    if config.mode != MODE:
        return []
    r = kubectl(config, f"get deployments -l {proj.MANAGED_BY} -o name")
    return sorted(line.split("/", 1)[1] for line in r.stdout.split() if "/" in line)


def app_rows(config: ClusterConfig) -> list[tuple[str, str, str, str]]:
    """(name, ready, nodes, url) for every app pi-cluster deployed."""
    r = kubectl(config, f"get deployments,services,pods -l {proj.MANAGED_BY} -o json")
    if r.returncode != 0:
        raise CLIError(f"Couldn't ask k3s about apps: {r.stderr.strip()}")
    items = json.loads(r.stdout).get("items", [])
    cp = config.control_plane
    assert cp is not None

    nodes: dict[str, set[str]] = {}
    ports: dict[str, int] = {}
    for item in items:
        name = item["metadata"].get("labels", {}).get("app.kubernetes.io/name", "?")
        if item["kind"] == "Pod" and item["spec"].get("nodeName"):
            nodes.setdefault(name, set()).add(item["spec"]["nodeName"])
        elif item["kind"] == "Service":
            for port in item["spec"].get("ports", []):
                if port.get("nodePort"):
                    ports[name] = port["nodePort"]

    rows = []
    for item in items:
        if item["kind"] != "Deployment":
            continue
        name = item["metadata"]["name"]
        ready = f"{item['status'].get('readyReplicas', 0)}/{item['spec'].get('replicas', 0)}"
        url = f"http://{cp.address}:{ports[name]}" if name in ports else "-"
        rows.append((name, ready, ", ".join(sorted(nodes.get(name, []))) or "-", url))
    return sorted(rows)


def app_logs(config: ClusterConfig, name: str, lines: int, follow: bool) -> None:
    cp = config.control_plane
    assert cp is not None
    selector = shlex.quote(proj.app_selector(name))
    command = (
        f"sudo -n k3s kubectl logs -l {selector} --all-containers --prefix "
        f"--tail {lines} --max-log-requests 20"
    )
    if follow:
        command += " -f"
    remote.stream(config, [cp], command)


# --------------------------------------------------------------------------- #
# cluster kubernetes <command>
# --------------------------------------------------------------------------- #
def cmd_config(args: argparse.Namespace) -> None:
    config = load_cluster()
    require_mode(config, MODE)
    cp = config.control_plane
    assert cp is not None
    result = remote.run(config, cp, "cat /etc/rancher/k3s/k3s.yaml")
    if result.returncode != 0:
        raise CLIError(f"Couldn't read the kubeconfig from {cp.name}.")
    text = result.stdout.replace("https://127.0.0.1:6443", f"https://{cp.address}:6443")
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    out.chmod(0o600)
    print(f"Wrote {out}. Use it with:\n\n  export KUBECONFIG={out}\n  kubectl get nodes")


def cmd_build(args: argparse.Namespace) -> None:
    config = load_cluster()
    require_mode(config, MODE)
    context = Path(args.dir)
    name = args.name or context.resolve().name.lower()
    build = images.plan(name, context, args.tag)
    cp = config.control_plane
    assert cp is not None
    print(f"Building {build.ref} on {cp.name} ...")
    build_images([build], force=args.force)
    print(
        f"\nPushed. Use it in your manifests as:\n\n  image: {build.ref}\n\n"
        f"({images.REGISTRY}/{name}:latest also points at this build.)"
    )


_LIST_REGISTRY = (
    "python3 -c 'import json,urllib.request as u\n"
    'b="http://localhost:30007/v2/"\n'
    'r=json.load(u.urlopen(b+"_catalog"))["repositories"]\n'
    'print(json.dumps({n:json.load(u.urlopen(b+n+"/tags/list")).get("tags") or [] '
    "for n in r}))'"
)


def cmd_registry(args: argparse.Namespace) -> None:
    config = load_cluster()
    require_mode(config, MODE)
    cp = config.control_plane
    assert cp is not None
    result = remote.run(config, cp, _LIST_REGISTRY)
    if result.returncode != 0:
        raise CLIError(f"Couldn't reach the registry: {result.stderr.strip()}")
    repos: dict[str, list[str]] = json.loads(result.stdout)
    print("Registry")
    print(f"  in your manifests : {images.REGISTRY}/<name>:<tag>")
    print(f"  from this machine : {cp.address}:{images.REGISTRY_PORT}  (plain HTTP, no login)")
    print("  pushing from here : see docs/registry.md\n")
    if not repos:
        print("No images yet. Build one with `cluster kubernetes build <folder>`.")
        return
    width = max(len(n) for n in repos)
    for name, tags in sorted(repos.items()):
        print(f"  {name:<{width}}  {', '.join(sorted(tags)) or '(no tags)'}")


def register(group: argparse._SubParsersAction) -> None:
    """Add the kubernetes-only commands under `cluster kubernetes`."""
    p = group.add_parser("config", help="fetch the kubeconfig so kubectl works from here")
    p.add_argument(
        "-o",
        "--output",
        default=KUBECONFIG_DEFAULT,
        help="where to write it (default: %(default)s)",
    )
    p.set_defaults(func=cmd_config)

    p = group.add_parser("build", help="build a Dockerfile folder into an image in the registry")
    p.add_argument("dir", help="folder containing a Dockerfile")
    p.add_argument("-t", "--name", help="image name (default: the folder's name)")
    p.add_argument("--tag", help="image tag (default: a hash of the folder's contents)")
    p.add_argument("--force", action="store_true", help="rebuild even if the tag exists")
    p.set_defaults(func=cmd_build)

    p = group.add_parser("registry", help="show the registry's address and the images in it")
    p.set_defaults(func=cmd_registry)
