# The k3s registry

The kubernetes mode runs a private image registry inside the cluster.

| From | Address |
| --- | --- |
| Inside the cluster (your manifests) | `localhost:30007/<name>:<tag>` |
| Your machine | `<any-node>:30007`, e.g. `pi-node-01.local:30007` |

It's plain HTTP with no login: fine on a home network, but anyone on your LAN
can push to or pull from it. `cluster kube registry` shows what's stored.

## Easiest: build on the cluster

```bash
cluster kube build ./web -t web
```

This copies the folder to the control-plane, builds it there (so it's ARM, and
you need no Docker locally), and pushes it as `localhost:30007/web:<hash>` and
`localhost:30007/web:latest`. Use the printed name in your YAML:

```yaml
containers:
  - name: web
    image: localhost:30007/web:3f2a9c1e0b7d
```

Prefer the hash tag over `latest`: a new tag is what makes Kubernetes roll out
the new version.

## Pushing from your own machine

If you'd rather build locally, you need an ARM64 image and to tell your tool
the registry is plain HTTP. Images pushed as `pi-node-01.local:30007/web` show
up in the cluster as `localhost:30007/web` — same registry, different name.

**Docker** — add to Docker's `daemon.json` (Docker Desktop: Settings → Docker
Engine) and restart Docker:

```json
{ "insecure-registries": ["pi-node-01.local:30007"] }
```

```bash
docker buildx build --platform linux/arm64 \
  --output type=image,name=pi-node-01.local:30007/web:v1,push=true,registry.insecure=true .
```

**Podman** — no config needed:

```bash
podman build --platform linux/arm64 -t pi-node-01.local:30007/web:v1 .
podman push --tls-verify=false pi-node-01.local:30007/web:v1
```

Then reference it as `localhost:30007/web:v1` in your manifests.

On WSL2, `.local` names often don't resolve; use the node's IP instead (from
`cluster status`).
