"""The ``cluster`` command-line interface.

Commands
--------
    cluster init      Generate an SSH key, discover the Pis, write config + inventory.
    cluster apply     Verify SSH to every node and run the base setup.
    cluster create    Apply a mode (e.g. `cluster create kubernetes`).
    cluster deploy    Build + deploy a mode's apps (e.g. the LED operator).
    cluster destroy   Tear a mode back down.
    cluster status    Check which nodes are reachable.
    cluster shutdown  Power off every node.
    cluster modes     List the available modes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cluster import __version__
from cluster.ansible_runner import data_path, run_playbook
from cluster.config import (
    CONTROL_PLANE,
    WORKER,
    ClusterConfig,
    Node,
    SSHConfig,
    StorageConfig,
    load_config,
    save_config,
)
from cluster.discovery import discover
from cluster.inventory import INVENTORY_FILENAME, write_inventory
from cluster.modes import MODES, get_mode
from cluster.ssh_keys import ensure_keypair, expand, public_key_text

BASE_PLAYBOOKS = data_path("playbooks")


def _die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> None:
    ssh = SSHConfig(
        username=args.username,
        private_key=args.key,
        hostname_prefix=args.prefix,
    )

    print(f"Ensuring SSH keypair at {ssh.private_key} ...")
    ensure_keypair(ssh.private_key)
    pub = public_key_text(ssh.private_key)

    print("\n" + "=" * 70)
    print("Flash each Pi with Raspberry Pi Imager using these custom settings:")
    print(f"  hostname : {ssh.hostname_prefix}-01, {ssh.hostname_prefix}-02, ...")
    print(f"  username : {ssh.username}")
    print("  enable SSH with this PUBLIC KEY:")
    print(f"    {pub}")
    print("See docs/flashing-guide.md for the full walkthrough.")
    print("=" * 70 + "\n")

    if args.no_discover:
        print("Skipping discovery (--no-discover). Edit cluster-config.json by hand.")
        config = ClusterConfig(ssh=ssh, storage=StorageConfig(mount=args.storage_mount))
        _finalise(config)
        return

    print("Discovering Pis on the network (this can take a moment) ...")
    found = discover(ssh.hostname_prefix, ssh.username, ssh.private_key, cidr=args.scan)
    if not found:
        _die(
            "No nodes found. Check the Pis are powered on and were flashed with the "
            "public key above, then retry — or pass --scan <CIDR>, or --no-discover "
            "to fill in cluster-config.json manually."
        )

    nodes = [
        Node(
            name=d.hostname,
            address=d.address,
            role=CONTROL_PLANE if i == 0 else WORKER,
        )
        for i, d in enumerate(found)
    ]
    storage = StorageConfig(node=nodes[0].name, mount=args.storage_mount)
    config = ClusterConfig(ssh=ssh, nodes=nodes, storage=storage)

    print(f"\nDiscovered {len(nodes)} node(s):")
    for n in nodes:
        tag = "control-plane" if n.is_control_plane else "worker"
        print(f"  - {n.name} ({n.address}) [{tag}]")
    print(f"Storage node (SSD/NFS): {storage.node}")

    _finalise(config)


def _finalise(config: ClusterConfig) -> None:
    cfg_path = save_config(config)
    print(f"\nWrote {cfg_path.name}")
    if config.control_plane:
        inv_path = write_inventory(config)
        print(f"Wrote {inv_path.name}")
        print("\nNext: `cluster apply` to verify connectivity, then "
              "`cluster create kubernetes`.")
    else:
        print("No control-plane node set yet — edit cluster-config.json, then run `cluster apply`.")


# --------------------------------------------------------------------------- #
# apply / status / shutdown
# --------------------------------------------------------------------------- #
def _load_and_sync() -> ClusterConfig:
    """Load config and regenerate inventory so the two never drift."""
    config = load_config()
    if not config.control_plane:
        _die("No control-plane node in cluster-config.json. Run `cluster init` or edit the file.")
    write_inventory(config)
    return config


def cmd_apply(args: argparse.Namespace) -> None:
    _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    print("Checking connectivity and running base setup ...")
    run_playbook(BASE_PLAYBOOKS / "check-cluster.yml", inventory)
    run_playbook(BASE_PLAYBOOKS / "base-setup.yml", inventory)
    print("\nCluster is reachable and base setup applied.")


def cmd_status(args: argparse.Namespace) -> None:
    _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    run_playbook(BASE_PLAYBOOKS / "check-cluster.yml", inventory)


def cmd_shutdown(args: argparse.Namespace) -> None:
    _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    run_playbook(BASE_PLAYBOOKS / "shutdown-cluster.yml", inventory)


# --------------------------------------------------------------------------- #
# create / destroy / modes
# --------------------------------------------------------------------------- #
def cmd_create(args: argparse.Namespace) -> None:
    mode = get_mode(args.mode)
    config = _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    mode_dir = data_path("modes", mode.name)

    print(f"Creating '{mode.name}' mode across {len(config.nodes)} node(s) ...")
    for pb in mode.create_playbooks:
        print(f"\n>>> {pb}")
        run_playbook(mode_dir / pb, inventory)

    config.mode = mode.name
    save_config(config)
    print(f"\n'{mode.name}' mode is up. Fetch kubeconfig from the control-plane to use kubectl.")


def cmd_deploy(args: argparse.Namespace) -> None:
    mode = get_mode(args.mode)
    config = _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    mode_dir = data_path("modes", mode.name)
    extra_vars = {"ssh_private_key": str(expand(config.ssh.private_key))}

    print(f"Deploying '{mode.name}' apps (building images on the control-plane) ...")
    for pb in mode.deploy_playbooks:
        print(f"\n>>> {pb}")
        run_playbook(mode_dir / pb, inventory, extra_vars=extra_vars)
    print("\nApps deployed. Create/delete a pod and watch the node LEDs flash.")


def cmd_destroy(args: argparse.Namespace) -> None:
    mode = get_mode(args.mode)
    _load_and_sync()
    inventory = Path.cwd() / INVENTORY_FILENAME
    mode_dir = data_path("modes", mode.name)
    for pb in mode.destroy_playbooks:
        print(f"\n>>> {pb}")
        run_playbook(mode_dir / pb, inventory)
    print(f"\n'{mode.name}' mode torn down.")


def cmd_modes(args: argparse.Namespace) -> None:
    print("Available modes:")
    for mode in MODES.values():
        print(f"  {mode.name:<12} {mode.summary}")


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cluster", description=__doc__)
    parser.add_argument("--version", action="version", version=f"pi-cluster {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="generate SSH key, discover Pis, write config + inventory")
    p_init.add_argument("--prefix", default="pi-node", help="hostname prefix (default: pi-node)")
    p_init.add_argument("--username", default="pi", help="SSH username on the Pis (default: pi)")
    p_init.add_argument("--key", default="~/.ssh/pi-cluster", help="SSH private key path")
    p_init.add_argument("--storage-mount", default="/mnt/ssd", help="mount point for the SSD")
    p_init.add_argument("--scan", metavar="CIDR", help="force a subnet scan of CIDR instead of mDNS")
    p_init.add_argument("--no-discover", action="store_true", help="skip discovery; edit config by hand")
    p_init.set_defaults(func=cmd_init)

    p_apply = sub.add_parser("apply", help="verify SSH and run base setup")
    p_apply.set_defaults(func=cmd_apply)

    p_create = sub.add_parser("create", help="apply a mode (e.g. kubernetes)")
    p_create.add_argument("mode", choices=sorted(MODES), help="mode to create")
    p_create.set_defaults(func=cmd_create)

    p_deploy = sub.add_parser("deploy", help="build + deploy a mode's apps (e.g. the LED operator)")
    p_deploy.add_argument("mode", choices=sorted(MODES), help="mode whose apps to deploy")
    p_deploy.set_defaults(func=cmd_deploy)

    p_destroy = sub.add_parser("destroy", help="tear a mode back down")
    p_destroy.add_argument("mode", choices=sorted(MODES), help="mode to destroy")
    p_destroy.set_defaults(func=cmd_destroy)

    p_status = sub.add_parser("status", help="check which nodes are reachable")
    p_status.set_defaults(func=cmd_status)

    p_shutdown = sub.add_parser("shutdown", help="power off every node")
    p_shutdown.set_defaults(func=cmd_shutdown)

    p_modes = sub.add_parser("modes", help="list available modes")
    p_modes.set_defaults(func=cmd_modes)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, RuntimeError, ValueError, KeyError) as exc:
        _die(str(exc))
    except KeyboardInterrupt:
        _die("interrupted")


if __name__ == "__main__":
    main()
