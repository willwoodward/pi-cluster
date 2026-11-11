"""The ``cluster`` command-line interface.

the nodes      init, apply, status, ssh, pubkey, shutdown, reset
modes          modes, switch, and one group per mode: cluster <mode> up | down | demo | ...
workloads      deploy, undeploy, ps, logs   (from cluster.toml)
LEDs           lights install | flash | firmware
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pi_cluster import __version__, images, kube, remote
from pi_cluster import project as proj
from pi_cluster.ansible_runner import data_path, run_playbook
from pi_cluster.cliutil import CLIError, confirm, load_cluster, ssh_vars
from pi_cluster.config import (
    CONTROL_PLANE,
    DEFAULT_HOSTNAME_PREFIX,
    DEFAULT_KEY_PATH,
    DEFAULT_STORAGE_DEVICE,
    DEFAULT_STORAGE_MOUNT,
    DEFAULT_USERNAME,
    WORKER,
    ClusterConfig,
    Node,
    SSHConfig,
    StorageConfig,
    config_exists,
    config_path,
    load_config,
    save_config,
)
from pi_cluster.discovery import discover, is_wsl
from pi_cluster.inventory import write_inventory
from pi_cluster.modes import MODES, Mode, get_mode
from pi_cluster.ssh_keys import ensure_keypair, public_key_text

DESCRIPTION = """\
Turn a stack of Raspberry Pis into a distributed-systems lab.

the nodes:  init, apply, status, ssh, pubkey, shutdown, reset
modes:      modes, switch <mode>, and per mode: cluster <mode> up | down | demo | ...
workloads:  deploy, undeploy, ps, logs   (from cluster.toml)
LEDs:       lights install | flash | firmware

Run `cluster <command> --help` for details.
"""


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> None:
    if config_exists() and not args.force:
        existing = load_config()
        if existing.nodes:
            raise CLIError(
                f"Already initialised ({config_path()}, {len(existing.nodes)} nodes). "
                "Use --force to re-discover and overwrite it."
            )

    ssh = SSHConfig(username=args.username, private_key=args.key, hostname_prefix=args.prefix)
    ensure_keypair(ssh.private_key)
    pub = public_key_text(ssh.private_key)

    print("Flash each Pi with Raspberry Pi Imager using these settings:")
    print(f"  hostname : {ssh.hostname_prefix}-01, {ssh.hostname_prefix}-02, ...")
    print(f"  username : {ssh.username}")
    print("  SSH      : public-key only, with this key:")
    print(f"\n{pub}\n")
    print(
        "Full walkthrough: https://github.com/willwoodward/pi-cluster/blob/main/docs/flashing-guide.md\n"
    )

    storage = StorageConfig(device=args.storage_device, mount=args.storage_mount)
    # Save the settings straight away, so a run before the Pis are flashed
    # still leaves a config behind and re-running `cluster init` just works.
    save_config(ClusterConfig(ssh=ssh, storage=storage))

    if args.no_discover:
        print(f"Skipped discovery. Add your nodes to {config_path()}, then run `cluster apply`.")
        return

    print("Looking for Pis on the network ...")
    found = discover(ssh.hostname_prefix, ssh.username, ssh.private_key, cidr=args.scan)
    if not found:
        hint = ""
        if is_wsl() and not args.scan:
            hint = (
                "\n\nYou're on WSL2, which usually can't see .local names or your LAN. "
                "Pass your LAN's subnet with --scan (e.g. --scan 192.168.1.0/24; find it "
                "with `ipconfig` in Windows), or turn on mirrored networking in .wslconfig."
            )
        raise CLIError(
            "No Pis found yet. Once they're flashed with the key above and booted, run "
            "`cluster init` again (or use --scan CIDR, or --no-discover to add nodes "
            "by hand)." + hint
        )

    nodes = [
        Node(name=d.hostname, address=d.address, role=CONTROL_PLANE if i == 0 else WORKER)
        for i, d in enumerate(found)
    ]
    if not args.no_storage:
        storage.node = nodes[0].name
    config = ClusterConfig(ssh=ssh, nodes=nodes, storage=storage)
    save_config(config)
    write_inventory(config)

    print(f"Found {len(nodes)} node(s):")
    for n in nodes:
        print(f"  {n.name:<16} {n.address:<20} {n.role}")
    print(f"SSD / NFS storage: {storage.node or 'none'} ")
    print(f"\nWrote {config_path()}")
    print("Next: `cluster apply` to run base setup on every node.")


def cmd_pubkey(args: argparse.Namespace) -> None:
    key = load_config().ssh.private_key if config_exists() else DEFAULT_KEY_PATH
    print(public_key_text(key))


def _check_reachable(config: ClusterConfig) -> dict:
    def probe(node: Node) -> dict:
        if not remote.port_open(node.address):
            return {"ok": False, "detail": "no SSH (port 22 closed or host unreachable)"}
        result = remote.run(config, node, "uptime -p", timeout=15)
        if result.returncode != 0:
            return {
                "ok": False,
                "detail": (result.stderr.strip().splitlines() or ["ssh failed"])[-1],
            }
        return {"ok": True, "detail": result.stdout.strip()}

    return remote.parallel(config.nodes, probe)


def _print_status(config: ClusterConfig, results: dict) -> None:
    print(f"mode: {config.mode or 'none (bare)'}\n")
    print(f"{'NODE':<16} {'ROLE':<14} {'ADDRESS':<20} STATUS")
    for n in config.nodes:
        r = results[n.name]
        state = "up" if r["ok"] else "DOWN"
        print(f"{n.name:<16} {n.role:<14} {n.address:<20} {state:<5} {r['detail']}")


def cmd_status(args: argparse.Namespace) -> None:
    config = load_cluster()
    results = _check_reachable(config)
    _print_status(config, results)
    if not all(r["ok"] for r in results.values()):
        sys.exit(1)


def cmd_apply(args: argparse.Namespace) -> None:
    config = load_cluster()
    results = _check_reachable(config)
    down = [name for name, r in results.items() if not r["ok"]]
    if down:
        _print_status(config, results)
        raise CLIError(f"Can't reach {', '.join(down)}; fix that before running base setup.")
    print(f"All {len(config.nodes)} node(s) reachable. Running base setup ...")
    run_playbook("playbooks/base-setup.yml")
    print("\nBase setup done. Nodes are bare and ready: `cluster kube up` or `cluster deploy`.")


def cmd_ssh(args: argparse.Namespace) -> None:
    config = load_config()
    node = config.find_node(args.node)
    command = " ".join(args.command) if args.command else None
    argv = remote.ssh_command(config, node, command, tty=command is None)
    os.execvp(argv[0], argv)


def cmd_shutdown(args: argparse.Namespace) -> None:
    config = load_cluster()
    confirm(f"Power off all {len(config.nodes)} nodes?", args.yes)
    run_playbook("playbooks/shutdown.yml")
    print("\nShutdown sent. Wait for the activity LEDs to stop before unplugging.")


def cmd_reset(args: argparse.Namespace) -> None:
    config = load_cluster()
    confirm(
        "Remove everything pi-cluster installed (modes, services, LED tool, packages) "
        "and reboot every node?",
        args.yes,
    )
    config.mode = None  # record intent first, so a half-finished reset isn't "kubernetes"
    save_config(config)
    run_playbook("playbooks/reset.yml")
    print("\nNodes are back to bare (base setup kept). They're rebooting now.")


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #
def cmd_modes(args: argparse.Namespace) -> None:
    active = load_config().mode if config_exists() else None
    for mode in MODES.values():
        marker = "*" if mode.name == active else " "
        aliases = f" (or: {', '.join(mode.aliases)})" if mode.aliases else ""
        print(f"{marker} {mode.name:<12} {mode.summary}{aliases}")
    print("\nActive: " + (active or "none (nodes are bare)"))
    print("Use `cluster <mode> up`, or `cluster switch <mode>` to replace the active one.")


def _up(config: ClusterConfig, mode: Mode, demo: bool) -> None:
    print(f"Bringing up '{mode.name}' on {len(config.nodes)} node(s) ...")
    config.mode = mode.name  # record before running, so a failed `up` can be taken down
    save_config(config)
    for pb in mode.create_playbooks:
        print(f"\n>>> {pb}")
        run_playbook(pb)
    if demo:
        _demo(config, mode)
    print(f"\n'{mode.name}' is up. {mode.next_steps}".rstrip())


def _demo(config: ClusterConfig, mode: Mode) -> None:
    if not mode.demo_playbooks:
        raise CLIError(f"'{mode.name}' has no demo.")
    with tempfile.TemporaryDirectory(prefix="pi-cluster-demo-") as tmp:
        extra = ssh_vars(config)
        if mode.demo_images:
            builds = [images.plan(n, data_path(d)) for n, d in mode.demo_images.items()]
            extra.update(images.build_vars(builds, Path(tmp)))
        for pb in mode.demo_playbooks:
            print(f"\n>>> {pb}")
            run_playbook(pb, extra_vars=extra)


def _down(config: ClusterConfig, mode: Mode) -> None:
    print(f"Taking down '{mode.name}' ...")
    for pb in mode.destroy_playbooks:
        print(f"\n>>> {pb}")
        run_playbook(pb)
    if config.mode == mode.name:
        config.mode = None
        save_config(config)


def cmd_mode_up(args: argparse.Namespace) -> None:
    config = load_cluster()
    mode = get_mode(args.mode)
    if config.mode and config.mode != mode.name:
        raise CLIError(
            f"'{config.mode}' is active. Run `cluster switch {mode.name}` to replace it, "
            f"or `cluster {config.mode} down` first."
        )
    _up(config, mode, args.demo)


def cmd_mode_down(args: argparse.Namespace) -> None:
    config = load_cluster()
    mode = get_mode(args.mode)
    if config.mode and config.mode != mode.name:
        raise CLIError(f"'{mode.name}' isn't active ('{config.mode}' is).")
    _down(config, mode)
    print(f"\n'{mode.name}' removed. Nodes are bare.")


def cmd_mode_demo(args: argparse.Namespace) -> None:
    config = load_cluster()
    mode = get_mode(args.mode)
    if config.mode != mode.name:
        raise CLIError(f"'{mode.name}' isn't active. Run `cluster {mode.name} up --demo`.")
    _demo(config, mode)
    print("\nDemo deployed. Create or delete a pod and watch the node LEDs.")


def cmd_switch(args: argparse.Namespace) -> None:
    config = load_cluster()
    mode = get_mode(args.mode)
    if config.mode == mode.name:
        print(f"'{mode.name}' is already active.")
        return
    if config.mode:
        _down(config, get_mode(config.mode))
    _up(config, mode, args.demo)


# --------------------------------------------------------------------------- #
# workloads (cluster.toml)
# --------------------------------------------------------------------------- #
def _load_project(path: str | None) -> proj.Project:
    found = Path(path) if path else proj.find_project()
    if found is None or not found.is_file():
        raise CLIError(
            f"No {proj.PROJECT_FILENAME} here or in any parent folder "
            f"(or pass -f PATH). See docs/cluster-toml.md."
        )
    return proj.load_project(found)


def _check_names(names: list[str]) -> None:
    for n in names:
        if n != "*" and not proj.SERVICE_NAME_RE.match(n):
            raise CLIError(f"Invalid name '{n}'.")


def cmd_deploy(args: argparse.Namespace) -> None:
    config = load_cluster()
    project = _load_project(args.file)
    services, apps = project.select(args.names)
    if apps:
        kube.require_mode(config, kube.MODE)  # fail before building anything

    if project.build_command and not args.no_build:
        print(f"Building: {project.build_command}")
        result = subprocess.run(project.build_command, shell=True, cwd=project.root)
        if result.returncode != 0:
            raise CLIError(f"Build failed (exit code {result.returncode}).")

    deployable = []
    if services:
        proj.check_artifacts(services)
        for svc in services:
            nodes = proj.target_nodes(svc, config)
            if not nodes:
                print(f"Skipping '{svc.name}': no nodes match on = {svc.on!r}.")
                continue
            deployable.append(svc)
            print(f"  {svc.name:<16} -> {', '.join(n.name for n in nodes)}")
    if not deployable and not apps:
        raise CLIError("Nothing to deploy.")

    if deployable:
        run_playbook("services/deploy.yml", extra_vars=proj.deployment_vars(deployable, config))
    if apps:
        kube.deploy_apps(config, apps)
    print("\nDeployed. `cluster ps` to check, `cluster logs <name> -f` to follow output.")


def cmd_undeploy(args: argparse.Namespace) -> None:
    config = load_cluster()
    if args.all:
        services, apps = ["*"], ["*"]
    elif args.names:
        _check_names(args.names)
        found = proj.find_project()
        if found:  # we know which is which
            project = proj.load_project(found)
            services = [n for n in args.names if n not in project.apps]
            apps = [n for n in args.names if n in project.apps]
        else:  # no cluster.toml: remove whatever has that name
            services, apps = list(args.names), list(args.names)
    else:
        project = _load_project(args.file)
        services, apps = list(project.services), list(project.apps)

    if services:
        run_playbook("services/remove.yml", extra_vars={"service_names": services})
    if apps:
        kube.remove_apps(config, apps)
    print("\nRemoved.")


def _service_rows(config: ClusterConfig) -> list[tuple[str, str, str, str]]:
    command = f"systemctl list-units --all --type=service --no-legend --plain '{proj.UNIT_PREFIX}*'"
    results = remote.parallel(config.nodes, lambda n: remote.run(config, n, command))
    rows = []
    for node in config.nodes:
        r = results[node.name]
        if r.returncode != 0:
            rows.append(("-", node.name, "unreachable", ""))
            continue
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].startswith(proj.UNIT_PREFIX):
                name = parts[0][len(proj.UNIT_PREFIX) :].removesuffix(".service")
                rows.append((name, node.name, parts[2], parts[3]))
    return rows


def cmd_ps(args: argparse.Namespace) -> None:
    config = load_cluster()
    services = _service_rows(config)
    apps = kube.app_rows(config) if config.mode == kube.MODE else []

    real_services = [r for r in services if r[0] != "-"]
    if real_services or not apps:
        print("SERVICES (systemd)")
        if real_services:
            print(f"  {'NAME':<20} {'NODE':<16} {'ACTIVE':<10} SUB")
            for name, node, active, sub in sorted(real_services):
                print(f"  {name:<20} {node:<16} {active:<10} {sub}")
        else:
            print("  none")
    for _, node, state, _ in services:
        if state == "unreachable":
            print(f"  ({node} is unreachable)")
    if apps:
        print("\nAPPS (k3s)")
        print(f"  {'NAME':<20} {'READY':<7} {'URL':<28} NODES")
        for name, ready, nodes, url in apps:
            print(f"  {name:<20} {ready:<7} {url:<28} {nodes}")
    if not real_services and not apps:
        print("\nNothing deployed yet. Add a cluster.toml and run `cluster deploy`.")


def cmd_logs(args: argparse.Namespace) -> None:
    config = load_cluster()
    name = args.name
    _check_names([name])

    project = proj.load_project(found) if (found := proj.find_project()) else None
    if project and name in project.apps:
        kube.app_logs(config, name, args.lines, args.follow)
        return

    unit = f"{proj.UNIT_PREFIX}{name}.service"
    nodes: list[Node] = []
    if project and name in project.services:
        nodes = proj.target_nodes(project.services[name], config)
    if not nodes:  # not in cluster.toml: look for it on the cluster
        if name in kube.app_names_on_cluster(config):
            kube.app_logs(config, name, args.lines, args.follow)
            return
        checks = remote.parallel(
            config.nodes, lambda n: remote.run(config, n, f"systemctl cat {unit} >/dev/null 2>&1")
        )
        nodes = [n for n in config.nodes if checks[n.name].returncode == 0]
    if not nodes:
        raise CLIError(f"Nothing called '{name}' is deployed.")

    command = f"sudo -n journalctl -u {unit} -n {args.lines} --no-pager -o short-iso"
    if args.follow:
        command += " -f"
    remote.stream(config, nodes, command)


# --------------------------------------------------------------------------- #
# lights
# --------------------------------------------------------------------------- #
def cmd_lights_install(args: argparse.Namespace) -> None:
    load_cluster()
    run_playbook("lights/install.yml")
    print("\n`cluster-led` is installed on every node. Try `cluster lights flash`.")


def cmd_lights_flash(args: argparse.Namespace) -> None:
    config = load_cluster()
    nodes = [config.find_node(r) for r in args.nodes] if args.nodes else config.nodes
    command = f"cluster-led {args.color} && sleep {args.seconds} && cluster-led off"
    results = remote.parallel(nodes, lambda n: remote.run(config, n, command))
    failed = False
    for node in nodes:
        r = results[node.name]
        if r.returncode == 0:
            print(f"{node.name}: flashed {args.color}")
        else:
            failed = True
            print(f"{node.name}: failed — {(r.stderr or r.stdout).strip() or 'unknown error'}")
    if failed:
        sys.exit(1)


def cmd_lights_firmware(args: argparse.Namespace) -> None:
    dest = Path(args.dest).expanduser()
    if dest.is_dir():
        dest = dest / "code.py"
    shutil.copyfile(data_path("lights", "trinkey", "code.py"), dest)
    print(f"Wrote {dest}. Copy it onto each Neo Trinkey's CIRCUITPY drive as code.py.")


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def _add_mode_group(sub: argparse._SubParsersAction, mode: Mode) -> None:
    """`cluster <mode> up | down | demo`, plus the mode's own commands."""
    group = sub.add_parser(
        mode.name, aliases=list(mode.aliases), help=mode.summary, description=mode.summary
    )
    group.set_defaults(mode=mode.name)
    actions = group.add_subparsers(
        title="commands", dest="action", required=True, metavar="<command>"
    )
    p = actions.add_parser("up", help=f"set up {mode.name} on the nodes")
    p.add_argument("--demo", action="store_true", help="also deploy the demo")
    p.set_defaults(func=cmd_mode_up)
    p = actions.add_parser("down", help=f"remove {mode.name}, leaving the nodes bare")
    p.set_defaults(func=cmd_mode_down)
    if mode.demo_playbooks:
        p = actions.add_parser("demo", help="deploy the demo apps")
        p.set_defaults(func=cmd_mode_demo)
    if mode.commands:
        importlib.import_module(mode.commands).register(actions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cluster",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"pi-cluster {__version__}")
    sub = parser.add_subparsers(
        title="commands", dest="command", required=True, metavar="<command>"
    )

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    def add_yes(p: argparse.ArgumentParser) -> None:
        p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")

    # setup
    p = add("init", cmd_init, "create the SSH key, discover the Pis, write the config")
    p.add_argument(
        "--prefix", default=DEFAULT_HOSTNAME_PREFIX, help="hostname prefix (default: %(default)s)"
    )
    p.add_argument(
        "--username", default=DEFAULT_USERNAME, help="SSH user on the Pis (default: %(default)s)"
    )
    p.add_argument("--key", default=DEFAULT_KEY_PATH, help="SSH private key (default: %(default)s)")
    p.add_argument("--scan", metavar="CIDR", help="scan this subnet instead of using mDNS names")
    p.add_argument(
        "--no-discover", action="store_true", help="write the config without discovering nodes"
    )
    p.add_argument(
        "--no-storage", action="store_true", help="no SSD; the registry uses local storage"
    )
    p.add_argument(
        "--storage-device",
        default=DEFAULT_STORAGE_DEVICE,
        help="SSD partition (default: %(default)s)",
    )
    p.add_argument(
        "--storage-mount",
        default=DEFAULT_STORAGE_MOUNT,
        help="SSD mount point (default: %(default)s)",
    )
    p.add_argument("--force", action="store_true", help="overwrite an existing config")

    add("pubkey", cmd_pubkey, "print the public key to give Raspberry Pi Imager")
    add("apply", cmd_apply, "check every node is reachable and run base setup")
    add("status", cmd_status, "show which nodes are up, and the active mode")

    p = add("ssh", cmd_ssh, "open a shell on a node (or run a command there)")
    p.add_argument("node", help="node name, or its number (e.g. 2)")
    p.add_argument("command", nargs=argparse.REMAINDER, help="command to run instead of a shell")

    p = add("shutdown", cmd_shutdown, "power off every node")
    add_yes(p)
    p = add("reset", cmd_reset, "remove everything pi-cluster installed and reboot (back to bare)")
    add_yes(p)

    # modes
    add("modes", cmd_modes, "list the modes and which one is active")
    p = add("switch", cmd_switch, "take the active mode down and bring another up")
    p.add_argument("mode", help=f"one of: {', '.join(sorted(MODES))}")
    p.add_argument("--demo", action="store_true", help="also deploy the new mode's demo")
    for mode in MODES.values():
        _add_mode_group(sub, mode)

    # workloads
    p = add("deploy", cmd_deploy, "build and deploy the services and apps in cluster.toml")
    p.add_argument("names", nargs="*", help="only these (default: everything)")
    p.add_argument("-f", "--file", help="path to cluster.toml (default: search upwards)")
    p.add_argument("--no-build", action="store_true", help="skip the [build] command")
    p = add("undeploy", cmd_undeploy, "stop and remove deployed services and apps")
    p.add_argument("names", nargs="*", help="what to remove (default: everything in cluster.toml)")
    p.add_argument("-f", "--file", help="path to cluster.toml (default: search upwards)")
    p.add_argument("--all", action="store_true", help="remove everything pi-cluster deployed")
    add("ps", cmd_ps, "list deployed services and apps")
    p = add("logs", cmd_logs, "show logs from every node or pod running a service or app")
    p.add_argument("name")
    p.add_argument("-f", "--follow", action="store_true", help="keep streaming new lines")
    p.add_argument(
        "-n", "--lines", type=int, default=50, help="lines of history (default: %(default)s)"
    )

    # lights
    p = add("lights", None, "Neo Trinkey LED helpers")
    lights = p.add_subparsers(dest="lights_command", required=True, metavar="<action>")
    lp = lights.add_parser("install", help="install the cluster-led tool on every node")
    lp.set_defaults(func=cmd_lights_install)
    lp = lights.add_parser("flash", help="flash node LEDs to check they work")
    lp.add_argument("nodes", nargs="*", help="node names or numbers (default: all)")
    lp.add_argument("--color", default="white", help="colour to flash (default: %(default)s)")
    lp.add_argument("--seconds", type=float, default=1.0, help="how long (default: %(default)s)")
    lp.set_defaults(func=cmd_lights_flash)
    lp = lights.add_parser("firmware", help="save the Trinkey firmware (code.py) locally")
    lp.add_argument("dest", nargs="?", default=".", help="file or folder (default: current folder)")
    lp.set_defaults(func=cmd_lights_firmware)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (CLIError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
