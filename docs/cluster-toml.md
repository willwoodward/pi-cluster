# `cluster.toml` reference

`cluster deploy` looks for `cluster.toml` in the current folder or any parent
(or use `-f path/to/cluster.toml`). It describes how to build your project and
what to run:

- **`[services.<name>]`** — a binary run under systemd on the nodes. Works on
  bare nodes or alongside any mode.
- **`[apps.<name>]`** — a container on k3s (needs the kubernetes mode).
  pi-cluster builds the image and writes the Kubernetes objects for you.

Names are shared: a name can't be both a service and an app, and
`cluster logs <name>` / `cluster undeploy <name>` work for either.

```toml
[build]
command = "cargo zigbuild --release --target aarch64-unknown-linux-musl"

[services.agent]
binary  = "target/aarch64-unknown-linux-musl/release/agent"
on      = "workers"
args    = ["--controller", "{{ control_plane }}:8080"]
env     = { RUST_LOG = "info", NODE_NAME = "{{ node_name }}" }
user    = "root"
groups  = ["kvm"]
files   = ["agent.yaml"]
restart = "always"
```

## `[build]`

| Key | Meaning |
| --- | --- |
| `command` | Shell command run in the folder holding `cluster.toml` before deploying. Optional; skip it for one deploy with `cluster deploy --no-build`. |

## `[services.<name>]`

Names are lowercase letters, digits and dashes. Each service becomes the
systemd unit `pi-cluster-<name>.service`, installed in `/opt/pi-cluster/<name>/`.

| Key | Default | Meaning |
| --- | --- | --- |
| `binary` | required | Path to the executable, relative to `cluster.toml`. |
| `on` | `"all"` | `"all"`, `"control-plane"`, `"workers"`, or a list of node names. |
| `args` | `[]` | Command-line arguments. |
| `env` | `{}` | Environment variables (strings or numbers). |
| `user` | SSH user | User the service runs as. Use `"root"` for things like creating cgroups or microVMs. |
| `groups` | `[]` | Extra groups, e.g. `["kvm"]` for `/dev/kvm`, `["dialout"]` for the LEDs. |
| `files` | `[]` | Extra files copied next to the binary (config files, etc.). |
| `restart` | `"on-failure"` | systemd `Restart=` policy: `no`, `always`, `on-failure`, `on-abnormal`, `on-abort`, `on-success`. |

### Placeholders

`args` and `env` values can use these, filled in separately for each node:

| Placeholder | Example |
| --- | --- |
| `{{ control_plane }}` | `192.168.1.11` (the control-plane's address) |
| `{{ control_plane_name }}` | `pi-node-01` |
| `{{ node_name }}` | `pi-node-03` |
| `{{ node_address }}` | `192.168.1.13` |

## What deploy does

1. Runs `[build] command`.
2. Checks every binary exists and isn't built for x86.
3. On each target node: copies the binary and files to
   `/opt/pi-cluster/<name>/`, writes the env file and systemd unit, and
   restarts the service if anything changed.
4. Checks the service is still running two seconds later; if not, prints its
   last log lines and fails.

Redeploying with nothing changed leaves running services alone.

## `[apps.<name>]`

```toml
[apps.web]
build     = "./web"            # folder with a Dockerfile — or: image = "nginx:stable-alpine"
replicas  = 3
port      = 8080               # the port your container listens on
node_port = 30500              # optional: pin the outside port (30000-32767)
env       = { LOG_LEVEL = "info" }
args      = ["--verbose"]
```

| Key | Default | Meaning |
| --- | --- | --- |
| `build` | — | Folder with a Dockerfile, relative to `cluster.toml`. Built on the control-plane, so it's ARM. |
| `image` | — | A ready-made image instead (it must have an arm64 build). Set exactly one of `build` / `image`. |
| `replicas` | `1` | How many pods. |
| `port` | none | Container port. If set, the app gets a NodePort Service, reachable at `http://<any-node>:<node port>`. |
| `node_port` | k3s picks | Fix the outside port. Needs `port`. |
| `env` | `{}` | Environment variables. |
| `args` | `[]` | Arguments for the container's entrypoint. |

What `cluster deploy` does for apps:

1. Packs each `build` folder (skipping `.git` and anything in `.dockerignore`)
   and tags it with a hash of its contents.
2. Builds it on the control-plane with buildah — unless that tag is already in
   the registry, so unchanged apps aren't rebuilt — and pushes it.
3. Generates a Deployment (and Service, if there's a `port`), applies it, and
   waits for the rollout. A failed rollout prints the pods and recent events.

`cluster ps` shows each app's ready count, URL and nodes. The objects carry the
label `app.kubernetes.io/managed-by=pi-cluster`, so you can still poke at them
with kubectl (`kubectl get all -l app.kubernetes.io/managed-by=pi-cluster`).

When you want something these keys can't express (volumes, probes, several
containers, …), that's the point to write your own YAML and use kubectl —
`cluster kube build` still handles the image. See [registry.md](registry.md).

## Related commands

```bash
cluster deploy agent        # just one service
cluster ps                  # every pi-cluster service on every node
cluster logs agent -f -n 100
cluster undeploy agent      # or: undeploy (everything in cluster.toml), undeploy --all
cluster logs web -f         # apps too: streams every pod's output
cluster ssh 2 systemctl status pi-cluster-agent
```

## Cross-compiling Rust

The Pis are `aarch64`. A static musl binary has no runtime dependencies, so it
runs on any Pi OS version:

```bash
rustup target add aarch64-unknown-linux-musl
cargo install cargo-zigbuild    # also needs zig: pip install ziglang, or your package manager
cargo zigbuild --release --target aarch64-unknown-linux-musl
```
