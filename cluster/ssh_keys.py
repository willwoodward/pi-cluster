"""Manage the dedicated SSH keypair pi-cluster uses to reach the nodes.

We generate a project-specific key (default ``~/.ssh/pi-cluster``) rather than
reuse a personal key, so the public half can be safely handed to the Raspberry
Pi Imager at flash time and the private half can be mounted into the cluster
without touching the user's other credentials.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def expand(path: str) -> Path:
    return Path(path).expanduser()


def ensure_keypair(private_key: str, comment: str = "pi-cluster") -> Path:
    """Create the keypair if it does not already exist. Returns the public-key path."""
    priv = expand(private_key)
    pub = priv.with_suffix(priv.suffix + ".pub") if priv.suffix else Path(str(priv) + ".pub")

    if priv.exists() and pub.exists():
        return pub

    priv.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ssh-keygen",
            "-t", "ed25519",
            "-f", str(priv),
            "-N", "",  # no passphrase: unattended provisioning
            "-C", comment,
        ],
        check=True,
    )
    priv.chmod(0o600)
    return pub


def public_key_text(private_key: str) -> str:
    pub = Path(str(expand(private_key)) + ".pub")
    return pub.read_text().strip()
