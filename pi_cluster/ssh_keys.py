"""The dedicated SSH keypair pi-cluster uses to reach the nodes.

A project-specific key (default ``~/.ssh/pi-cluster``) rather than a personal
one, so the public half can be handed to Raspberry Pi Imager and the private
half mounted into the cluster without touching your other credentials.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def public_key_path(private_key: str) -> Path:
    return Path(str(Path(private_key).expanduser()) + ".pub")


def ensure_keypair(private_key: str, comment: str = "pi-cluster") -> Path:
    """Create the keypair if it doesn't exist yet. Returns the public-key path."""
    priv = Path(private_key).expanduser()
    pub = public_key_path(private_key)
    if priv.exists() and pub.exists():
        return pub
    if priv.exists() != pub.exists():
        raise RuntimeError(
            f"Only one half of the keypair exists ({priv} / {pub}). "
            "Remove the leftover file or pass a different --key."
        )
    if shutil.which("ssh-keygen") is None:
        raise RuntimeError("ssh-keygen not found; install OpenSSH.")
    priv.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-f", str(priv), "-N", "", "-C", comment],
        check=True,
    )
    priv.chmod(0o600)
    return pub


def public_key_text(private_key: str) -> str:
    pub = public_key_path(private_key)
    if not pub.exists():
        raise FileNotFoundError(f"No public key at {pub}. Run `cluster init` first.")
    return pub.read_text().strip()
