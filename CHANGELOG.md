# Changelog

## 0.1.0 — unreleased

First release.

- `cluster` CLI: `init`, `apply`, `status`, `ssh`, `pubkey`, `shutdown`, `reset`.
- Discovery by mDNS names (`pi-node-NN.local`), falling back to a subnet scan.
- Config in `~/.config/pi-cluster/` (override with `PI_CLUSTER_HOME`).
- Base setup: hostname and memory cgroups.
- Modes, one active at a time: `create`, `switch`, `destroy`, `demo`.
- `kubernetes` mode: k3s, an NFS- or locally-backed registry, an nginx example,
  and an optional demo with an LED pod-operator and a Flask app.
- `cluster.toml` services: `deploy`, `undeploy`, `ps`, `logs`.
- Neo Trinkey LEDs: `cluster lights install | flash | firmware`.
- `cluster reset` removes everything pi-cluster installed and reboots.
