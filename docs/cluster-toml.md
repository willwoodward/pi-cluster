# `cluster.toml` reference

`cluster deploy` looks for `cluster.toml` in the current folder or any parent
(or use `-f path/to/cluster.toml`). It describes how to build your project and
which binaries to run on which nodes.

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

## Related commands

```bash
cluster deploy agent        # just one service
cluster ps                  # every pi-cluster service on every node
cluster logs agent -f -n 100
cluster undeploy agent      # or: undeploy (everything in cluster.toml), undeploy --all
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
