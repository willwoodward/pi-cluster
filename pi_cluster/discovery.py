"""Find the Raspberry Pis on the network.

Two strategies, tried in order:

1. **mDNS names** — Pis flashed as ``pi-node-01``, ``pi-node-02``, … advertise
   themselves as ``pi-node-NN.local``. We probe those names in parallel.
2. **Subnet scan** — sweep a subnet for hosts with SSH open. Used when mDNS
   finds nothing, or straight away with ``cluster init --scan CIDR``.

A host only counts if it accepts the project SSH key, so unrelated machines
are never picked up.
"""

from __future__ import annotations

import ipaddress
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pi_cluster.remote import port_open, ssh_base

MAX_MDNS_INDEX = 32  # probe pi-node-01 … pi-node-32


@dataclass
class DiscoveredNode:
    hostname: str  # what `hostname` reports on the node
    address: str  # how we reached it: "pi-node-01.local" or an IP


def _ssh_hostname(address: str, username: str, private_key: str) -> str | None:
    try:
        result = subprocess.run(
            [*ssh_base(username, private_key, address), "hostname"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _probe(address: str, username: str, private_key: str) -> DiscoveredNode | None:
    if not port_open(address):
        return None
    hostname = _ssh_hostname(address, username, private_key)
    return DiscoveredNode(hostname, address) if hostname else None


def discover_via_mdns(
    prefix: str, username: str, private_key: str, max_index: int = MAX_MDNS_INDEX
) -> list[DiscoveredNode]:
    addresses = [f"{prefix}-{i:02d}.local" for i in range(1, max_index + 1)]
    with ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        results = pool.map(lambda a: _probe(a, username, private_key), addresses)
    return [r for r in results if r]


def local_subnet() -> str | None:
    """Best-effort guess at this machine's /24 from the default route."""
    try:
        out = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        # e.g. "1.1.1.1 via 192.168.2.1 dev eth0 src 192.168.2.57 uid 1000"
        parts = out.split()
        src = parts[parts.index("src") + 1]
        return str(ipaddress.ip_network(f"{src}/24", strict=False))
    except (OSError, ValueError, IndexError, subprocess.CalledProcessError):
        return None


def discover_via_scan(
    cidr: str, username: str, private_key: str, workers: int = 128
) -> list[DiscoveredNode]:
    network = ipaddress.ip_network(cidr, strict=False)
    if network.num_addresses > 4096:
        raise ValueError(f"{cidr} is too large to scan; use a /20 or smaller.")
    hosts = [str(ip) for ip in network.hosts()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        open_hosts = [h for h, ok in zip(hosts, pool.map(port_open, hosts), strict=True) if ok]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = pool.map(lambda h: _probe(h, username, private_key), open_hosts)
    return [r for r in results if r]


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        return False


def discover(
    prefix: str, username: str, private_key: str, cidr: str | None = None
) -> list[DiscoveredNode]:
    """Discover nodes, preferring mDNS and falling back to a subnet scan.

    Passing ``cidr`` skips mDNS and scans that subnet.
    """
    if cidr:
        nodes = discover_via_scan(cidr, username, private_key)
    else:
        nodes = discover_via_mdns(prefix, username, private_key)
        if not nodes:
            detected = local_subnet()
            if detected:
                print(f"No mDNS names found; scanning {detected} ...")
                nodes = discover_via_scan(detected, username, private_key)
    # Hostnames can repeat if a node answered on both mDNS and IP; keep the first.
    unique = {}
    for n in nodes:
        unique.setdefault(n.hostname, n)
    return sorted(unique.values(), key=lambda n: n.hostname)
