# pi-cluster

Turn a stack of Raspberry Pis into a hands-on distributed-systems lab.

`pi-cluster` installs a `cluster` command that finds the Pis on your network
and keeps them in a known **bare** state. On top of that you can:

- **switch modes** — whole environments such as a [k3s](https://k3s.io/)
  Kubernetes cluster, which you can tear down again cleanly;
- **run your own things** — describe them in a `cluster.toml` (a Rust
  controller on one node and agents on the rest, or containers on k3s) and
  `cluster deploy` builds, ships and runs them. Or drive k3s with kubectl
  yourself, for learning;
- **flash LEDs** — an optional [Neo Trinkey](https://www.adafruit.com/product/4870)
  per node, so you can *see* where work lands.

`cluster reset` takes every node back to bare whenever you want a clean slate
to experiment with cgroups, namespaces, KVM or anything else by hand.

## What you need

- 2 or more Raspberry Pis running 64-bit Raspberry Pi OS (Lite is plenty).
- A network switch (PoE keeps the wiring tidy).
- Optional: an SSD on one Pi, exported over NFS to back the k3s registry.
- Optional: a Neo Trinkey per node.
- On your machine: Python 3.10+ and OpenSSH. Linux, macOS and WSL2 all work.

## Install

```bash
pipx install pi-cluster      # or: pip install pi-cluster
```

This installs the `cluster` command (also available as `pi-cluster`) along with
Ansible, which it uses under the hood.

## Quick start

```bash
cluster init       # creates an SSH key and prints the settings to flash with
```

Flash each Pi with Raspberry Pi Imager as `pi-node-01`, `pi-node-02`, … using
that key; [docs/flashing-guide.md](docs/flashing-guide.md) walks through it.
Boot them, then:

```bash
cluster init           # run again now they're up, to discover them
cluster apply          # check SSH to every node and run base setup
cluster status         # who's up, and what mode is active
```

`pi-node-01` becomes the control-plane; the rest are workers. Everything is
recorded in `~/.config/pi-cluster/config.json` (edit it to change roles or the
storage node), so `cluster` works from any folder.

## Modes

A mode is a whole environment layered on bare nodes. Only one is active at a
time, and each has its own command group named after it:

```bash
cluster modes                     # list them, and which is active
cluster kubernetes up             # bring one up (aliases: kube, k3s)
cluster kubernetes down           # back to bare
cluster switch <mode>             # take the active mode down, bring another up
```

Every mode has `up`, `down` and (if it has one) `demo`, plus its own extras.

### kubernetes

`cluster kube up`:

1. installs the k3s server on the control-plane and joins the workers;
2. mounts the SSD on the storage node and exports it over NFS (skipped if you
   have no SSD — the registry then uses local storage);
3. deploys a private registry at `localhost:30007` on every node, plus an nginx
   example at `http://<any-node>:30080`.

Its own commands:

```bash
cluster kube config               # write ~/.kube/pi-cluster.yaml so kubectl works from here
cluster kube build ./web -t web   # build a Dockerfile folder on the cluster, push it to the registry
cluster kube registry             # registry address and the images in it
cluster kube demo                 # the LED pod-operator and a Flask example
```

The demo (also `cluster kube up --demo`) rolls out:

- the **LED pod-operator**, a [kopf](https://kopf.readthedocs.io/) operator
  that flashes a node's LEDs green when a pod lands on it and red when one
  leaves;
- a **Flask example** at `http://<any-node>:30005` that reports which node
  served you.

Images are always built on the control-plane (so they're ARM, and you don't
need Docker here) with buildah, and tagged by a hash of their contents.

There are two ways to run your own things on k3s:

- **By hand with kubectl** — the way to learn Kubernetes. Write your own YAML,
  use `cluster kube build` to get images into the registry, and `kubectl apply`.
  [docs/registry.md](docs/registry.md) covers pushing from your own machine too.
- **With `cluster.toml`** — when you just want something running, without
  kubectl. See below.

## Running your own things: `cluster.toml`

Put a `cluster.toml` in your project. It can hold two kinds of workload:

- **`[services]`** — binaries run under systemd on the nodes, with or without a
  mode (great for your own Rust distributed systems);
- **`[apps]`** — containers on k3s (kubernetes mode). pi-cluster builds the
  image and writes the Deployment and Service for you.

```toml
[build]
command = "cargo zigbuild --release --target aarch64-unknown-linux-musl"

[services.controller]
binary = "target/aarch64-unknown-linux-musl/release/controller"
on = "control-plane"
args = ["--listen", "0.0.0.0:8080"]

[services.agent]
binary = "target/aarch64-unknown-linux-musl/release/agent"
on = "workers"
args = ["--controller", "{{ control_plane }}:8080"]
env = { NODE_NAME = "{{ node_name }}" }

[apps.web]
build = "./web"          # a folder with a Dockerfile (or: image = "nginx:stable-alpine")
replicas = 3
port = 8080
```

Then, from that folder, the same commands cover both:

```bash
cluster deploy              # build, ship, (re)start — only what changed
cluster ps                  # what's running where (services and apps)
cluster logs agent -f       # follow output from every node or pod running it
cluster undeploy            # stop and remove everything in cluster.toml
```

Services run as `pi-cluster-<name>.service` from `/opt/pi-cluster/<name>/`;
`cluster deploy` refuses x86 binaries, which catches the most common mistake.
See [docs/cluster-toml.md](docs/cluster-toml.md) for every option, and
[examples/hello-agent](examples/hello-agent) for a working Rust controller and
agent to start from.

## LEDs

Each Neo Trinkey needs firmware once:

```bash
cluster lights firmware     # saves code.py — copy it onto the Trinkey's CIRCUITPY drive
cluster lights install      # installs the `cluster-led` tool on every node
cluster lights flash        # flash every node white to check they're working
cluster lights flash 2 --color green
```

Your own services can call `cluster-led <colour>` on the node too (they need
`groups = ["dialout"]` in `cluster.toml` if they don't run as the SSH user).

## Back to bare

```bash
cluster reset
```

Uninstalls k3s, removes deployed services, the LED tool, and every apt package
pi-cluster installed (it keeps a record per node, so packages you installed
yourself are left alone), then reboots to clear leftover kernel state such as
iptables rules. Base setup — hostname and memory cgroups — is kept.

It only removes what pi-cluster added. To undo changes you made by hand,
reflash.

## All commands

**The nodes**

| Command | What it does |
| --- | --- |
| `cluster init` | Create the SSH key, discover the Pis, write the config. |
| `cluster pubkey` | Print the public key for Raspberry Pi Imager. |
| `cluster apply` | Check every node is reachable and run base setup. |
| `cluster status` | Which nodes are up, and the active mode. |
| `cluster ssh <node> [cmd]` | Shell on a node (`cluster ssh 2` works). |
| `cluster shutdown` | Power off every node (workers first). |
| `cluster reset` | Remove everything pi-cluster installed; reboot. |

**Modes**

| Command | What it does |
| --- | --- |
| `cluster modes` | List modes and which is active. |
| `cluster switch <mode> [--demo]` | Replace the active mode. |
| `cluster <mode> up [--demo]` | Bring a mode up. |
| `cluster <mode> down` | Take it down, leaving the nodes bare. |
| `cluster <mode> demo` | Deploy the mode's demo. |
| `cluster kube config` | Fetch the kubeconfig for kubectl. |
| `cluster kube build <dir> [-t name]` | Build an image on the cluster and push it to the registry. |
| `cluster kube registry` | Registry address and images. |

**Workloads (`cluster.toml`)**

| Command | What it does |
| --- | --- |
| `cluster deploy [name…]` | Build and deploy services and apps. |
| `cluster undeploy [name…] [--all]` | Stop and remove them. |
| `cluster ps` | What's running where. |
| `cluster logs <name> [-f]` | Logs from every node or pod running it. |

**LEDs**

| Command | What it does |
| --- | --- |
| `cluster lights install` | Install `cluster-led` on every node. |
| `cluster lights flash [node…]` | Flash LEDs to check they work. |
| `cluster lights firmware` | Save the Trinkey firmware locally. |

## Troubleshooting

- **Discovery finds nothing.** Check the Pis are booted and were flashed with
  the key from `cluster pubkey`. If `.local` names don't resolve on your
  network, scan instead: `cluster init --scan 192.168.1.0/24`.
- **On WSL2.** WSL usually can't see `.local` names or your LAN subnet. Use
  `--scan` with your LAN's subnet (run `ipconfig` in Windows to find it), or
  enable `networkingMode=mirrored` in `.wslconfig`.
- **A node shows DOWN.** `cluster ssh <node>` shows the raw SSH error.
- **Wrong roles or storage node.** Edit `~/.config/pi-cluster/config.json`
  (`storage.node: null` means no SSD) and re-run `cluster apply`.
- **Deploy says the binary is x86.** Build for `aarch64-unknown-linux-musl`;
  [cargo-zigbuild](https://github.com/rust-cross/cargo-zigbuild) is the easiest
  way from Linux, macOS or WSL.
- **Config location.** Set `PI_CLUSTER_HOME` to keep several clusters apart.

## Contributing

Development uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync                    # create .venv with pi-cluster + dev tools
uv run cluster --help      # run the CLI from your checkout
uv run pytest              # tests (including Ansible syntax checks)
uv run ruff format .       # format
uv run ruff check .        # lint
uv run ty check            # type-check
```

CI runs all of these on every push and pull request.

New modes are a folder of playbooks plus one registry entry; see
[docs/adding-a-mode.md](docs/adding-a-mode.md).

## Releasing

The version lives in `pyproject.toml`. To release:

```bash
uv version --bump minor    # or patch / major, or e.g. `uv version 1.0.0`
```

Update `CHANGELOG.md`, then merge to `main`. The release workflow notices the
new version, runs CI, publishes to PyPI, and tags the commit `vX.Y.Z` with a
GitHub release. Merges that don't change the version don't release anything.

## License

[MIT](LICENSE)
