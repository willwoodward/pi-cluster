import json

import pytest

from pi_cluster.config import (
    CONTROL_PLANE,
    ClusterConfig,
    Node,
    config_dir,
    config_path,
    load_config,
    save_config,
)


def test_round_trip(cluster):
    loaded = load_config()
    assert loaded.to_dict() == cluster.to_dict()
    assert loaded.control_plane is not None
    assert loaded.control_plane.name == "pi-node-01"
    assert [n.name for n in loaded.workers] == ["pi-node-02", "pi-node-03"]
    storage = loaded.storage_node()
    assert storage is not None
    assert storage.name == "pi-node-01"


def test_config_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("PI_CLUSTER_HOME")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_dir() == tmp_path / "xdg" / "pi-cluster"


def test_missing_config_points_at_init():
    with pytest.raises(FileNotFoundError, match="cluster init"):
        load_config()


def test_legacy_config_in_cwd_is_migrated(tmp_path, cluster):
    config_path().unlink()
    legacy = tmp_path / "work" / "cluster-config.json"
    legacy.write_text(json.dumps(cluster.to_dict()))
    assert load_config().to_dict() == cluster.to_dict()
    assert config_path().exists()
    assert legacy.exists()  # copied, never deleted


def test_unknown_keys_are_a_clear_error():
    config_path().parent.mkdir(parents=True)
    config_path().write_text(json.dumps({"nodes": [{"name": "a", "adress": "x"}]}))
    with pytest.raises(ValueError, match="Invalid cluster config"):
        load_config()


@pytest.mark.parametrize(
    "nodes, message",
    [
        ([], "No nodes"),
        ([Node("a", "1.1.1.1")], "Exactly one node"),
        ([Node("a", "1", CONTROL_PLANE), Node("a", "2")], "listed twice"),
        ([Node("a", "1", CONTROL_PLANE), Node("b", "2", CONTROL_PLANE)], "Exactly one node"),
        ([Node("a", "1", "boss")], "has role"),
        ([Node("bad name", "1", CONTROL_PLANE)], "Invalid node name"),
    ],
)
def test_validate(nodes, message):
    with pytest.raises(ValueError, match=message):
        ClusterConfig(nodes=nodes).validate()


def test_storage_node_must_exist(cluster):
    cluster.storage.node = "pi-node-99"
    with pytest.raises(ValueError, match=r"storage\.node"):
        cluster.validate()


def test_find_node_by_name_or_number(cluster):
    assert cluster.find_node("pi-node-03").name == "pi-node-03"
    assert cluster.find_node("2").name == "pi-node-02"
    with pytest.raises(ValueError, match="No node called"):
        cluster.find_node("7")


def test_save_is_atomic_and_readable(cluster):
    cluster.mode = "kubernetes"
    save_config(cluster)
    assert json.loads(config_path().read_text())["mode"] == "kubernetes"
    assert not list(config_path().parent.glob("*.tmp"))
