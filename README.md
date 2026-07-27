# pi-cluster

Turn a stack of Raspberry Pis into a hands-on distributed-systems lab.

`pi-cluster` gives you a `cluster` command-line tool that discovers the Pis on
your network, generates an Ansible inventory, and applies a **mode** — a
self-contained distributed-systems environment. The first mode is a
[k3s](https://k3s.io/) Kubernetes cluster with a private registry, example
apps, and an optional **LED pod-visualiser** that flashes a light on the
physical node where a pod lands.

The mode system is designed to grow: future modes (a Raft demo, MPI, a gossip
protocol) can reuse the same discovery, inventory, and LED machinery.

## Hardware

- 2 or more Raspberry Pis (any mix; the tool adapts to however many it finds).
- A network switch — PoE keeps the wiring tidy.
- Optional: an SSD on one Pi, exported over NFS to back the registry.
- Optional: an [Adafruit Neo Trinkey](https://www.adafruit.com/product/4870)
  per node for the LED visualiser.

## Install

```bash
pip install pi-cluster        # or: pipx install pi-cluster
```

This installs the `cluster` command and `ansible-core`.

## Getting started

### 1. Flash the SD cards / SSDs

Follow [docs/flashing-guide.md](docs/flashing-guide.md). In short: flash each Pi
with Raspberry Pi Imager, giving it the hostname `pi-node-01`, `pi-node-02`, …,
a shared username, and the SSH public key that `cluster init` generates.

### 2. Discover and connect

```bash
cluster init      # generate SSH key, discover the Pis, write config + inventory
cluster apply     # verify SSH into every node and run base setup
```

`cluster init` writes two files in the current directory:

- `cluster-config.json` — the editable source of truth (nodes, roles, storage).
- `inventory.ini` — the Ansible inventory, regenerated from the config on every
  command.

The lowest-numbered node becomes the control-plane; the rest become workers.

### 3. Bring up a mode

```bash
cluster modes                 # list available modes
cluster create kubernetes     # install k3s + registry + example apps
```

You now have a working k3s cluster. Fetch the kubeconfig from the control-plane
node (`/etc/rancher/k3s/k3s.yaml`) to drive it with `kubectl`.

### 4. Deploy the apps (optional)

```bash
cluster deploy kubernetes     # build + push images, roll out the LED operator + Flask app
```

Then create or delete a pod and watch the LED flash on the node it lands on
(green = created, red = deleted). See [the LED visualiser](#led-pod-visualiser).

## Commands

| Command | What it does |
| --- | --- |
| `cluster init` | Generate the SSH key, discover the Pis, write config + inventory. |
| `cluster apply` | Verify SSH to every node and run base setup. |
| `cluster create <mode>` | Apply a mode (e.g. `kubernetes`). |
| `cluster deploy <mode>` | Build + deploy the mode's apps (e.g. the LED operator). |
| `cluster destroy <mode>` | Tear a mode back down. |
| `cluster status` | Check which nodes are reachable. |
| `cluster shutdown` | Power off every node. |
| `cluster modes` | List available modes. |

## The kubernetes mode

`cluster create kubernetes` runs, in order:

1. **install** — install the k3s server on the control-plane and join the workers.
2. **setup-nfs** — export the SSD over NFS from the storage node.
3. **configure-registry** — point k3s at the in-cluster registry mirror.
4. **deploy** — apply the private registry and the nginx example.

### LED pod-visualiser

`cluster deploy kubernetes` builds the images **on the control-plane node**
(so they're the right architecture), pushes them to the in-cluster registry, and
rolls out:

- the **`pod-operator`** — a [kopf](https://kopf.readthedocs.io/) operator that
  watches pod create/delete events and SSHes into the affected node to flash its
  Neo Trinkey LED (green on create, red on delete). Its SSH key comes from a
  mounted Kubernetes Secret, never baked into the image;
- the **Flask example** app.

**Hardware:** flash each Neo Trinkey with the CircuitPython firmware at
`cluster/data/modes/kubernetes/lights/code.py` (copy it onto the Trinkey as
`code.py`). `cluster deploy` installs the matching host script on every node.
Test one node directly with:

```bash
python cluster/data/modes/kubernetes/lights/light-flash.py <node-ip>
```

## Layout

```
cluster/
  cli.py            # the `cluster` command
  config.py         # cluster-config.json model
  discovery.py      # mDNS + subnet discovery
  inventory.py      # config -> inventory.ini
  ansible_runner.py # runs bundled playbooks
  modes.py          # registry of modes
  data/
    playbooks/      # base playbooks (setup, status, shutdown)
    modes/
      kubernetes/   # install/deploy playbooks, manifests, LED scripts
docs/
  flashing-guide.md
```

## Troubleshooting

- **Discovery finds nothing.** Check the Pis are powered and booted, and were
  flashed with the public key printed by `cluster init`. If mDNS `.local` names
  don't resolve on your network, force a subnet scan:
  `cluster init --scan 192.168.1.0/24`.
- **`ansible-playbook not found`.** Install it with `pip install ansible-core`.
- **Wrong node numbering.** Edit `cluster-config.json` (roles and storage node)
  and re-run `cluster apply`.

## License

[MIT](LICENSE)
