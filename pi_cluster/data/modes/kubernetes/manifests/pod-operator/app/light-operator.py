"""Flash a node's LED when a pod lands on it (green) or leaves it (red).

Uses kopf *event* handlers, which observe pods without adding finalizers or
writing annotations to them — so if this operator is down, nothing else in the
cluster is affected. Pods get a node some time after they're created, so we
flash when a pod is first seen with ``spec.nodeName`` set, not on creation.
"""

import logging
import os
import subprocess
import threading

import kopf
import kubernetes

SSH_KEY = os.environ.get("SSH_KEY_PATH", "/etc/pi-cluster/ssh/id")
SSH_USER = os.environ.get("NODE_SSH_USER", "pi")
FLASH_SECONDS = float(os.environ.get("FLASH_SECONDS", "0.5"))

_core = None
_placed = {}  # pod uid -> node name, for pods we've already seen on a node
_lock = threading.Lock()


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    global _core
    kubernetes.config.load_incluster_config()
    _core = kubernetes.client.CoreV1Api()
    settings.posting.level = logging.WARNING  # don't spam Events for every flash


def _node_ip(node_name):
    node = _core.read_node(node_name)
    for address in node.status.addresses or []:
        if address.type == "InternalIP":
            return address.address
    return None


def _flash(node_name, colour, logger):
    ip = _node_ip(node_name)
    if ip is None:
        logger.warning("Node %s has no InternalIP; can't flash it.", node_name)
        return
    command = f"cluster-led {colour} && sleep {FLASH_SECONDS} && cluster-led off"
    ssh = [
        "ssh",
        "-i",
        SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "LogLevel=ERROR",
        f"{SSH_USER}@{ip}",
        command,
    ]
    try:
        result = subprocess.run(ssh, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        logger.warning("Flashing %s timed out.", node_name)
        return
    if result.returncode != 0:
        logger.warning("Flashing %s failed: %s", node_name, result.stderr.strip())


@kopf.on.event("pods")
def on_pod_event(type, body, uid, name, namespace, logger, **_):
    node = (body.get("spec") or {}).get("nodeName")
    with _lock:
        previous = _placed.get(uid)
        if type == "DELETED":
            _placed.pop(uid, None)
        elif node:
            _placed[uid] = node

    if type is None:  # initial listing at startup: remember pods, don't flash
        return
    if type == "DELETED":
        target = previous or node
        if target:
            logger.info("Pod %s/%s left %s", namespace, name, target)
            _flash(target, "red", logger)
    elif node and previous is None:
        logger.info("Pod %s/%s landed on %s", namespace, name, node)
        _flash(node, "green", logger)
