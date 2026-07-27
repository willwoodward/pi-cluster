"""Discover the Raspberry Pis on the network.

Two strategies, tried in order:

1. **mDNS hostname probe** — if the Pis were flashed with the naming convention
   (``pi-node-01``, ``pi-node-02``, ...) they advertise themselves as
   ``pi-node-NN.local`` over Avahi/Bonjour. We probe those names directly, which
   is robust across a router/switch subnet and needs no IP scanning.

2. **Subnet scan** — fall back to sweeping the local /24 for hosts with SSH open,
   for networks where mDNS is unavailable.

In both cases a node only counts if it accepts our project SSH key, so we never
pick up unrelated machines.
"""

from __future__ import annotations

import ipaddress
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from cluster.ssh_keys import expand

SSH_PORT = 22
DEFAULT_PROBE_COUNT = 32  # highest index probed for the mDNS convention
CONSECUTIVE_MISSES_STOP = 4  # stop probing indices after this many gaps in a row


@dataclass
class DiscoveredNode:
    hostname: str  # reported hostname (from `hostname` on the node)
    address: str  # how we reached it: "pi-node-01.local" or an IP


# --------------------------------------------------------------------------- #
# Low-level probes
# --------------------------------------------------------------------------- #
def _port_open(host: str, port: int = SSH_PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ssh_hostname(address: str, username: str, private_key: str, timeout: int = 5) -> Optional[str]:
    """Return the node's hostname if our key authenticates, else None."""
    result = subprocess.run(
        [
            "ssh",
            "-i", str(expand(private_key)),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={timeout}",
            f"{username}@{address}",
            "hostname",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _probe(address: str, username: str, private_key: str) -> Optional[DiscoveredNode]:
    if not _port_open(address):
        return None
    hostname = _ssh_hostname(address, username, private_key)
    if hostname is None:
        return None
    return DiscoveredNode(hostname=hostname, address=address)


# --------------------------------------------------------------------------- #
# Strategy 1: mDNS hostname convention
# --------------------------------------------------------------------------- #
def discover_via_mdns(
    prefix: str,
    username: str,
    private_key: str,
    max_index: int = DEFAULT_PROBE_COUNT,
) -> List[DiscoveredNode]:
    found: List[DiscoveredNode] = []
    consecutive_misses = 0
    for index in range(1, max_index + 1):
        address = f"{prefix}-{index:02d}.local"
        node = _probe(address, username, private_key)
        if node:
            found.append(node)
            consecutive_misses = 0
        else:
            consecutive_misses += 1
            if consecutive_misses >= CONSECUTIVE_MISSES_STOP and found:
                break
    return found


# --------------------------------------------------------------------------- #
# Strategy 2: subnet scan
# --------------------------------------------------------------------------- #
def local_subnet() -> Optional[str]:
    """Best-effort detection of the machine's /24 from the default route."""
    try:
        out = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True, text=True, check=True,
        ).stdout
        # e.g. "1.1.1.1 via 192.168.2.1 dev eth0 src 192.168.2.57 uid 1000"
        parts = out.split()
        src = parts[parts.index("src") + 1]
        return str(ipaddress.ip_network(f"{src}/24", strict=False))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def discover_via_scan(
    cidr: str,
    username: str,
    private_key: str,
    workers: int = 64,
) -> List[DiscoveredNode]:
    hosts = [str(ip) for ip in ipaddress.ip_network(cidr, strict=False).hosts()]
    # Fast first pass: which hosts even have SSH open?
    with ThreadPoolExecutor(max_workers=workers) as pool:
        open_hosts = [h for h, ok in zip(hosts, pool.map(_port_open, hosts)) if ok]
    # Slower second pass: which of those accept our key?
    found: List[DiscoveredNode] = []
    with ThreadPoolExecutor(max_workers=min(workers, 16)) as pool:
        for node in pool.map(lambda h: _probe(h, username, private_key), open_hosts):
            if node:
                found.append(node)
    return found


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def discover(
    prefix: str,
    username: str,
    private_key: str,
    cidr: Optional[str] = None,
) -> List[DiscoveredNode]:
    """Discover nodes, preferring mDNS and falling back to a subnet scan.

    If ``cidr`` is given, the scan strategy is forced (skipping mDNS).
    """
    if cidr:
        nodes = discover_via_scan(cidr, username, private_key)
    else:
        nodes = discover_via_mdns(prefix, username, private_key)
        if not nodes:
            detected = local_subnet()
            if detected:
                nodes = discover_via_scan(detected, username, private_key)
    # Deterministic order: by hostname so index 01 sorts first.
    return sorted(nodes, key=lambda n: n.hostname)
