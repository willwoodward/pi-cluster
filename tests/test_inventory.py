from pathlib import Path

from pi_cluster.inventory import inventory_path, render_inventory, write_inventory


def _section(text, name):
    lines = text.splitlines()
    start = lines.index(f"[{name}]") + 1
    out = []
    for line in lines[start:]:
        if line.startswith("[") or not line:
            break
        out.append(line)
    return out


def test_groups(cluster):
    text = render_inventory(cluster)
    assert _section(text, "control_plane") == ["pi-node-01 ansible_host=192.168.1.11"]
    assert _section(text, "workers") == [
        "pi-node-02 ansible_host=192.168.1.12",
        "pi-node-03 ansible_host=192.168.1.13",
    ]
    assert _section(text, "storage") == ["pi-node-01 ansible_host=192.168.1.11"]


def test_vars(cluster):
    text = render_inventory(cluster)
    key = Path("~/.ssh/pi-cluster").expanduser()
    assert f"ansible_ssh_private_key_file={key}" in text
    assert "ansible_user=pi" in text
    assert "storage_mount=/mnt/ssd" in text


def test_no_storage_leaves_group_empty(cluster):
    cluster.storage.node = None
    assert _section(render_inventory(cluster), "storage") == []


def test_written_next_to_config(cluster, isolated_home):
    path = write_inventory(cluster)
    assert path == inventory_path() == isolated_home / "inventory.ini"
    assert path.read_text() == render_inventory(cluster)
