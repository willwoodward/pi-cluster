# hello-agent

A tiny Rust controller and agent, with no dependencies — a starting point for
your own cluster software.

- `controller` runs on the control-plane, collects heartbeats, and lists the
  agents it has heard from at `GET /`.
- `agent` runs on every worker and sends a heartbeat every few seconds.

## Run it

```bash
rustup target add aarch64-unknown-linux-musl
cargo install cargo-zigbuild        # needs zig too: pip install ziglang

cluster deploy                      # builds, then deploys both services
curl http://pi-node-01.local:8080/  # the agents should appear within seconds
cluster logs agent -f
cluster undeploy
```

See [cluster.toml](cluster.toml) and the
[reference](../../docs/cluster-toml.md).
