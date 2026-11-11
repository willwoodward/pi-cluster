# Changelog

## 0.1.0 — unreleased

First release.

- `cluster` CLI: `init`, `apply`, `status`, `ssh`, `pubkey`, `shutdown`, `reset`.
- Discovery by mDNS names (`pi-node-NN.local`), falling back to a subnet scan.
- Config in `~/.config/pi-cluster/` (override with `PI_CLUSTER_HOME`).
- Base setup: hostname and memory cgroups.
- Modes, one active at a time, each with its own command group:
  `cluster <mode> up | down | demo`, plus `cluster modes` and `cluster switch`.
- `kubernetes` mode (aliases `kube`, `k3s`): k3s, an NFS- or locally-backed
  registry, an nginx example, an optional demo with an LED pod-operator and a
  Flask app, and `cluster kube config | build | registry`.
- `cluster.toml` with `[services]` (systemd binaries) and `[apps]` (k3s
  containers), driven by `deploy`, `undeploy`, `ps`, `logs`.
- Neo Trinkey LEDs: `cluster lights install | flash | firmware`.
- `cluster reset` removes everything pi-cluster installed and reboots.
