"""Helpers shared by the top-level CLI and the per-mode command groups."""

from __future__ import annotations

import sys
from pathlib import Path

from pi_cluster.config import ClusterConfig, load_config
from pi_cluster.inventory import write_inventory


class CLIError(Exception):
    """A user-facing error: printed without a traceback."""


def confirm(prompt: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise CLIError(f"{prompt} Re-run with --yes to confirm.")
    answer = input(f"{prompt} [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise CLIError("Cancelled.")


def load_cluster() -> ClusterConfig:
    """Load and validate the config, and regenerate the inventory from it."""
    config = load_config()
    config.validate()
    write_inventory(config)
    return config


def require_mode(config: ClusterConfig, mode: str) -> None:
    if config.mode != mode:
        active = f"'{config.mode}' is active" if config.mode else "no mode is active"
        raise CLIError(
            f"This needs the {mode} mode, but {active}. Run `cluster {mode} up` "
            f"(or `cluster switch {mode}`) first."
        )


def ssh_vars(config: ClusterConfig) -> dict:
    return {"ssh_private_key": str(Path(config.ssh.private_key).expanduser())}
