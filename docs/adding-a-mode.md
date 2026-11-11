# Adding a mode

A mode is a folder of Ansible playbooks under `pi_cluster/data/modes/<name>/`
plus one entry in `pi_cluster/modes.py`.

```python
"raft": Mode(
    name="raft",
    summary="A Raft demo across every node.",
    aliases=("rf",),                 # optional: `cluster rf up` works too
    create_playbooks=["modes/raft/install.yml"],      # cluster raft up
    destroy_playbooks=["modes/raft/uninstall.yml"],   # cluster raft down
    demo_playbooks=[],               # optional: cluster raft demo
    commands="pi_cluster.raft",      # optional: extra `cluster raft …` commands
    next_steps="Try `cluster raft status`.",
),
```

Playbook paths are relative to `pi_cluster/data/`.

## The mode's command group

Every mode gets `cluster <mode> up | down` (and `demo`, if it has demo
playbooks) for free. For anything else, point `commands` at a module with a
`register(subparsers)` function — see `pi_cluster/kube.py`, which adds
`cluster kubernetes config | build | registry`:

```python
from pi_cluster.cliutil import load_cluster, require_mode


def cmd_status(args):
    config = load_cluster()
    require_mode(config, "raft")
    ...


def register(group):
    p = group.add_parser("status", help="show the Raft leader and term")
    p.set_defaults(func=cmd_status)
```

Keep cluster-wide verbs (`deploy`, `ps`, `logs`) at the top level; a mode's
group is for things that only make sense in that mode.

## What's available to playbooks

- Groups: `control_plane`, `workers`, `storage` (may be empty), `all`.
- Variables: `ansible_user`, `storage_device`, `storage_mount`,
  `storage_fstype`, and `pi_cluster_data` (the absolute path of the `data/`
  folder, for `src:` paths and includes).

## Rules that keep `down` and `reset` honest

1. **Install apt packages through the tracked task**, so they're removed
   exactly:

   ```yaml
   - name: Install what the mode needs
     ansible.builtin.include_tasks: "{{ pi_cluster_data }}/tasks/apt-install.yml"
     vars:
       packages: [some-package]
       component: raft
   ```

   and in `uninstall.yml`:

   ```yaml
   - ansible.builtin.include_tasks: "{{ pi_cluster_data }}/tasks/apt-remove.yml"
     vars:
       component: raft
   ```

2. **Keep your own state under `/var/lib/pi-cluster/<mode>/`** and remove it in
   `uninstall.yml`.
3. **Make every playbook safe to run twice.** `up` re-runs on an active
   mode, and `down` runs against half-built ones.
4. **Add your `uninstall.yml` to `playbooks/reset.yml`.**

A test (`tests/test_package_data.py`) syntax-checks every playbook listed in
`MODES`, so `pytest` catches typos.
