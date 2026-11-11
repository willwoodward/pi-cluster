"""``cluster.toml``: run your own things on the cluster without wiring them up by hand.

Two kinds of workload, driven by the same ``cluster deploy / ps / logs / undeploy``:

- ``[services.<name>]`` — a binary run under systemd on bare nodes (any mode).
- ``[apps.<name>]`` — a container on k3s (kubernetes mode). pi-cluster builds
  the image on the control-plane and generates the Deployment and Service, so
  you don't need kubectl. (For hand-written YAML, use kubectl directly.)

A project (say, a Rust repo) describes its services::

    [build]
    command = "cargo zigbuild --release --target aarch64-unknown-linux-musl"

    [services.agent]
    binary = "target/aarch64-unknown-linux-musl/release/agent"
    on = "workers"
    args = ["--controller", "http://{{ control_plane }}:8080"]
    env = { RUST_LOG = "info" }

Each service is installed to ``/opt/pi-cluster/<name>/`` and run by the unit
``pi-cluster-<name>.service``. Values in ``args`` and ``env`` can use
``{{ control_plane }}``, ``{{ control_plane_name }}``, ``{{ node_name }}`` and
``{{ node_address }}``, filled in per node.

And apps::

    [apps.web]
    build = "./web"          # a folder with a Dockerfile; or image = "nginx:stable"
    replicas = 3
    port = 8080              # exposed on every node through a NodePort
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from pi_cluster.config import ClusterConfig, Node

PROJECT_FILENAME = "cluster.toml"
SERVICE_ROOT = "/opt/pi-cluster"
UNIT_PREFIX = "pi-cluster-"
TARGET_GROUPS = ("all", "control-plane", "workers")
RESTART_POLICIES = ("no", "always", "on-failure", "on-abnormal", "on-abort", "on-success")

SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]*$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

_SERVICE_KEYS = {"binary", "on", "args", "env", "user", "groups", "files", "restart"}
_APP_KEYS = {"build", "image", "replicas", "port", "node_port", "env", "args"}

MANAGED_BY = "app.kubernetes.io/managed-by=pi-cluster"


@dataclass
class Service:
    name: str
    binary: Path  # absolute path on this machine
    on: str | list[str] = "all"  # "all" | "control-plane" | "workers" | [node names]
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    user: str | None = None  # None = the cluster's SSH user
    groups: list[str] = field(default_factory=list)  # extra groups, e.g. ["kvm"]
    files: list[Path] = field(default_factory=list)  # copied next to the binary
    restart: str = "on-failure"

    @property
    def unit_name(self) -> str:
        return f"{UNIT_PREFIX}{self.name}.service"

    @property
    def directory(self) -> str:
        return f"{SERVICE_ROOT}/{self.name}"


@dataclass
class App:
    name: str
    build: Path | None = None  # build context (folder with a Dockerfile), absolute
    image: str | None = None  # or a ready-made image, e.g. "nginx:stable-alpine"
    replicas: int = 1
    port: int | None = None  # container port; exposed through a NodePort Service
    node_port: int | None = None  # pin the NodePort (30000-32767); default: k3s picks
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)


@dataclass
class Project:
    root: Path
    build_command: str | None
    services: dict[str, Service]
    apps: dict[str, App] = field(default_factory=dict)

    @property
    def names(self) -> list[str]:
        return [*self.services, *self.apps]

    def select(self, names: list[str]) -> tuple[list[Service], list[App]]:
        if not names:
            return list(self.services.values()), list(self.apps.values())
        unknown = [n for n in names if n not in self.services and n not in self.apps]
        if unknown:
            raise ValueError(
                f"Nothing called {', '.join(unknown)} in {PROJECT_FILENAME}. "
                f"Defined: {', '.join(self.names) or '(none)'}."
            )
        return (
            [self.services[n] for n in names if n in self.services],
            [self.apps[n] for n in names if n in self.apps],
        )


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def find_project(start: Path | None = None) -> Path | None:
    """Find cluster.toml in ``start`` or any parent directory."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / PROJECT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _str_list(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where} must be a list of strings.")
    return list(value)


def _parse_env(env, where: str) -> dict[str, str]:
    if not isinstance(env, dict):
        raise ValueError(f"{where}: `env` must be a table.")
    clean: dict[str, str] = {}
    for key, value in env.items():
        if not _ENV_KEY_RE.match(key):
            raise ValueError(f"{where}: invalid environment variable name '{key}'.")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"{where}: env.{key} must be a string or number.")
        clean[key] = str(value)
    return clean


def _int(raw: dict, key: str, where: str, low: int, high: int) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{where}: `{key}` must be a whole number from {low} to {high}.")
    return value


def _check_name(name: str, where: str) -> None:
    # Also a valid Kubernetes object name (DNS label): no trailing dash.
    if not SERVICE_NAME_RE.match(name) or name.endswith("-"):
        raise ValueError(f"{where}: names must be lowercase letters, digits and dashes.")


def _parse_app(name: str, raw: dict, root: Path) -> App:
    where = f"[apps.{name}]"
    _check_name(name, where)
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be a table.")
    unknown = set(raw) - _APP_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}.")

    build, image = raw.get("build"), raw.get("image")
    if (build is None) == (image is None):
        raise ValueError(f"{where}: set exactly one of `build` (a folder) or `image`.")
    if build is not None and not isinstance(build, str):
        raise ValueError(f"{where}: `build` must be a path to a folder with a Dockerfile.")
    if image is not None and (not isinstance(image, str) or not image.strip()):
        raise ValueError(f"{where}: `image` must be an image name, e.g. 'nginx:stable'.")

    replicas = _int(raw, "replicas", where, 0, 100)
    port = _int(raw, "port", where, 1, 65535)
    node_port = _int(raw, "node_port", where, 30000, 32767)
    if node_port is not None and port is None:
        raise ValueError(f"{where}: `node_port` needs `port` too.")

    return App(
        name=name,
        build=(root / build).resolve() if build else None,
        image=image,
        replicas=1 if replicas is None else replicas,
        port=port,
        node_port=node_port,
        env=_parse_env(raw.get("env", {}), where),
        args=_str_list(raw.get("args", []), f"{where} `args`"),
    )


def _parse_service(name: str, raw: dict, root: Path) -> Service:
    where = f"[services.{name}]"
    _check_name(name, where)
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be a table.")
    unknown = set(raw) - _SERVICE_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}.")
    if not isinstance(raw.get("binary"), str):
        raise ValueError(f"{where}: `binary` (path to the executable) is required.")

    on = raw.get("on", "all")
    if isinstance(on, str):
        if on not in TARGET_GROUPS:
            raise ValueError(
                f"{where}: `on` must be one of {', '.join(TARGET_GROUPS)} or a list of node names."
            )
    else:
        on = _str_list(on, f"{where} `on`")
        if not on:
            raise ValueError(f"{where}: `on` is an empty list.")

    clean_env = _parse_env(raw.get("env", {}), where)

    user = raw.get("user")
    if user is not None and (not isinstance(user, str) or not _USER_RE.match(user)):
        raise ValueError(f"{where}: invalid `user`.")
    groups = _str_list(raw.get("groups", []), f"{where} `groups`")
    for g in groups:
        if not _USER_RE.match(g):
            raise ValueError(f"{where}: invalid group '{g}'.")

    restart = raw.get("restart", "on-failure")
    if restart not in RESTART_POLICIES:
        raise ValueError(f"{where}: `restart` must be one of {', '.join(RESTART_POLICIES)}.")

    files = [(root / f).resolve() for f in _str_list(raw.get("files", []), f"{where} `files`")]
    binary = (root / raw["binary"]).resolve()
    taken = {binary.name, "env"}  # everything lands flat in /opt/pi-cluster/<name>/
    for f in files:
        if f.name in taken:
            raise ValueError(f"{where}: two files would both be installed as '{f.name}'.")
        taken.add(f.name)
    args = _str_list(raw.get("args", []), f"{where} `args`")
    for value in args + list(clean_env.values()):
        if "\n" in value or "\r" in value:
            raise ValueError(f"{where}: args and env values can't contain newlines.")

    return Service(
        name=name,
        binary=binary,
        on=on,
        args=args,
        env=clean_env,
        user=user,
        groups=groups,
        files=files,
        restart=restart,
    )


def load_project(path: Path) -> Project:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: {exc}") from None

    unknown = set(data) - {"build", "services", "apps"}
    if unknown:
        raise ValueError(f"{path}: unknown section(s) {', '.join(sorted(unknown))}.")

    build = data.get("build", {})
    if not isinstance(build, dict) or set(build) - {"command"}:
        raise ValueError(f"{path}: [build] only supports `command`.")
    command = build.get("command")
    if command is not None and not isinstance(command, str):
        raise ValueError(f"{path}: build.command must be a string.")

    raw_services = data.get("services", {})
    raw_apps = data.get("apps", {})
    if not isinstance(raw_services, dict) or not isinstance(raw_apps, dict):
        raise ValueError(f"{path}: [services] and [apps] must be tables.")
    if not raw_services and not raw_apps:
        raise ValueError(f"{path}: define at least one [services.<name>] or [apps.<name>].")
    both = set(raw_services) & set(raw_apps)
    if both:
        raise ValueError(f"{path}: '{sorted(both)[0]}' is both a service and an app.")

    root = path.parent.resolve()
    services = {name: _parse_service(name, raw, root) for name, raw in raw_services.items()}
    apps = {name: _parse_app(name, raw, root) for name, raw in raw_apps.items()}
    return Project(root=root, build_command=command, services=services, apps=apps)


# --------------------------------------------------------------------------- #
# Resolving against a cluster
# --------------------------------------------------------------------------- #
def target_nodes(service: Service, config: ClusterConfig) -> list[Node]:
    if service.on == "all":
        return list(config.nodes)
    if service.on == "control-plane":
        return [config.control_plane] if config.control_plane else []
    if service.on == "workers":
        return config.workers
    nodes = []
    assert isinstance(service.on, list)
    for name in service.on:
        node = config.node(name)
        if node is None:
            raise ValueError(f"Service '{service.name}' targets unknown node '{name}'.")
        nodes.append(node)
    return nodes


def render(value: str, context: dict[str, str]) -> str:
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(
                f"Unknown placeholder {{{{ {key} }}}}. Available: {', '.join(sorted(context))}."
            )
        return context[key]

    return _PLACEHOLDER_RE.sub(sub, value)


def node_context(config: ClusterConfig, node: Node) -> dict[str, str]:
    cp = config.control_plane
    return {
        "control_plane": cp.address if cp else "",
        "control_plane_name": cp.name if cp else "",
        "node_name": node.name,
        "node_address": node.address,
    }


def systemd_quote(arg: str) -> str:
    """Quote one ExecStart argument so systemd passes it through unchanged."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return f'"{escaped}"'


def env_file(env: dict[str, str]) -> str:
    lines = []
    for key, value in env.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    return "\n".join(lines) + ("\n" if lines else "")


def unit_file(service: Service, user: str, args: list[str]) -> str:
    exec_start = " ".join(
        [f"{service.directory}/{service.binary.name}"] + [systemd_quote(a) for a in args]
    )
    lines = [
        "# Managed by pi-cluster. Changes are overwritten by `cluster deploy`.",
        "[Unit]",
        f"Description=pi-cluster service {service.name}",
        "Wants=network-online.target",
        "After=network-online.target",
        "",
        "[Service]",
        f"User={user}",
    ]
    if service.groups:
        lines.append(f"SupplementaryGroups={' '.join(service.groups)}")
    lines += [
        f"WorkingDirectory={service.directory}",
        f"EnvironmentFile={service.directory}/env",
        f"ExecStart={exec_start}",
        f"Restart={service.restart}",
        "RestartSec=2",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ]
    return "\n".join(lines)


def deployment_vars(services: list[Service], config: ClusterConfig) -> dict:
    """The data the deploy playbook needs, rendered per node."""
    payload = []
    for svc in services:
        user = svc.user or config.ssh.username
        hosts = {}
        for node in target_nodes(svc, config):
            ctx = node_context(config, node)
            args = [render(a, ctx) for a in svc.args]
            env = {k: render(v, ctx) for k, v in svc.env.items()}
            hosts[node.name] = {"unit": unit_file(svc, user, args), "env": env_file(env)}
        payload.append(
            {
                "name": svc.name,
                "unit_name": svc.unit_name,
                "directory": svc.directory,
                "binary": str(svc.binary),
                "binary_name": svc.binary.name,
                "files": [str(f) for f in svc.files],
                "user": user,
                "groups": svc.groups,
                "hosts": hosts,
            }
        )
    return {"services": payload}


# --------------------------------------------------------------------------- #
# Pre-flight checks on the local files
# --------------------------------------------------------------------------- #
_ELF_MACHINES = {3: "x86", 40: "32-bit ARM", 62: "x86-64", 183: "aarch64"}


def elf_machine(path: Path) -> str | None:
    """Return the CPU architecture an ELF binary targets, or None if not ELF."""
    with path.open("rb") as fh:
        header = fh.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        return None
    order = "little" if header[5] == 1 else "big"
    machine = int.from_bytes(header[18:20], order)
    return _ELF_MACHINES.get(machine, f"machine type {machine}")


def check_artifacts(services: list[Service]) -> None:
    for svc in services:
        if not svc.binary.is_file():
            raise FileNotFoundError(
                f"Service '{svc.name}': binary {svc.binary} not found. Did the build run?"
            )
        arch = elf_machine(svc.binary)
        if arch in ("x86", "x86-64"):
            raise ValueError(
                f"Service '{svc.name}': {svc.binary.name} is an {arch} binary, but the Pis "
                "are ARM. Build for aarch64-unknown-linux-musl (or -gnu), e.g. with "
                "`cargo zigbuild --release --target aarch64-unknown-linux-musl`."
            )
        for f in svc.files:
            if not f.is_file():
                raise FileNotFoundError(f"Service '{svc.name}': file {f} not found.")


# --------------------------------------------------------------------------- #
# Apps -> Kubernetes objects
# --------------------------------------------------------------------------- #
def app_labels(name: str) -> dict[str, str]:
    return {"app.kubernetes.io/name": name, "app.kubernetes.io/managed-by": "pi-cluster"}


def app_selector(name: str) -> str:
    return f"app.kubernetes.io/name={name},{MANAGED_BY}"


def app_manifest(app: App, image: str) -> str:
    """A Deployment (plus a NodePort Service if the app has a port), as JSON."""
    labels = app_labels(app.name)
    container: dict = {"name": app.name, "image": image}
    if app.args:
        container["args"] = app.args
    if app.env:
        container["env"] = [{"name": k, "value": v} for k, v in app.env.items()]
    if app.port:
        container["ports"] = [{"containerPort": app.port}]

    items: list[dict] = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": app.name, "labels": labels},
            "spec": {
                "replicas": app.replicas,
                "selector": {"matchLabels": {"app.kubernetes.io/name": app.name}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {"containers": [container]},
                },
            },
        }
    ]
    if app.port:
        port: dict = {"protocol": "TCP", "port": app.port, "targetPort": app.port}
        if app.node_port:
            port["nodePort"] = app.node_port
        items.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": app.name, "labels": labels},
                "spec": {
                    "type": "NodePort",
                    "selector": {"app.kubernetes.io/name": app.name},
                    "ports": [port],
                },
            }
        )
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, indent=2) + "\n"
