# Adding a mode

A mode is a folder of Ansible playbooks under `pi_cluster/data/modes/<name>/`
plus one entry in `pi_cluster/modes.py`.

```python
"raft": Mode(
    name="raft",
    summary="A Raft demo across every node.",
    create_playbooks=["modes/raft/install.yml"],
    destroy_playbooks=["modes/raft/uninstall.yml"],
    demo_playbooks=[],          # optional extras for `cluster demo`
    next_steps="Try `cluster logs raft -f`.",
),
```

Playbook paths are relative to `pi_cluster/data/`.

## What's available to playbooks

- Groups: `control_plane`, `workers`, `storage` (may be empty), `all`.
- Variables: `ansible_user`, `storage_device`, `storage_mount`,
  `storage_fstype`, and `pi_cluster_data` (the absolute path of the `data/`
  folder, for `src:` paths and includes).

## Rules that keep `destroy` and `reset` honest

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
3. **Make every playbook safe to run twice.** `create` re-runs on an active
   mode, and `destroy` runs against half-built ones.
4. **Add your `uninstall.yml` to `playbooks/reset.yml`.**

A test (`tests/test_package_data.py`) syntax-checks every playbook listed in
`MODES`, so `pytest` catches typos.
