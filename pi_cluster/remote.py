"""Run commands on the nodes over SSH, one at a time or all in parallel."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

from pi_cluster.config import ClusterConfig, Node

SSH_PORT = 22
T = TypeVar("T")


def ssh_base(username: str, private_key: str, address: str, connect_timeout: int = 5) -> list[str]:
    return [
        "ssh",
        "-i",
        str(Path(private_key).expanduser()),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        f"{username}@{address}",
    ]


def ssh_command(
    config: ClusterConfig, node: Node, command: str | None = None, tty: bool = False
) -> list[str]:
    cmd = ssh_base(config.ssh.username, config.ssh.private_key, node.address)
    if tty:
        cmd.insert(1, "-t")
    if command:
        cmd.append(command)
    return cmd


def port_open(host: str, port: int = SSH_PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run(
    config: ClusterConfig, node: Node, command: str, timeout: float | None = 30
) -> subprocess.CompletedProcess:
    """Run ``command`` on ``node``; never raises for a failed command."""
    try:
        return subprocess.run(
            ssh_command(config, node, command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess([], 124, "", "timed out")


def parallel(nodes: Sequence[Node], fn: Callable[[Node], T]) -> dict[str, T]:
    """Apply ``fn`` to every node concurrently; results keyed by node name."""
    if not nodes:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(nodes), 32)) as pool:
        results = list(pool.map(fn, nodes))
    return {n.name: r for n, r in zip(nodes, results, strict=True)}


def stream(config: ClusterConfig, nodes: Sequence[Node], command: str) -> int:
    """Run ``command`` on every node, printing output prefixed with the node name.

    Blocks until all commands exit (or Ctrl-C). Returns the worst exit code.
    """
    width = max(len(n.name) for n in nodes)
    lock = threading.Lock()
    procs: list[subprocess.Popen] = []

    def pump(node: Node, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            with lock:
                sys.stdout.write(f"{node.name:<{width}} | {line}")
                sys.stdout.flush()

    threads = []
    for node in nodes:
        proc = subprocess.Popen(
            ssh_command(config, node, command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        procs.append(proc)
        t = threading.Thread(target=pump, args=(node, proc), daemon=True)
        t.start()
        threads.append(t)
    try:
        for t in threads:
            t.join()
        return max((p.wait() for p in procs), default=0)
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        raise
