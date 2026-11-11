import pytest

from pi_cluster.config import (
    CONTROL_PLANE,
    WORKER,
    ClusterConfig,
    Node,
    StorageConfig,
    save_config,
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own config dir and working directory."""
    home = tmp_path / "config"
    monkeypatch.setenv("PI_CLUSTER_HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


@pytest.fixture
def cluster():
    config = ClusterConfig(
        nodes=[
            Node("pi-node-01", "192.168.1.11", CONTROL_PLANE),
            Node("pi-node-02", "192.168.1.12", WORKER),
            Node("pi-node-03", "192.168.1.13", WORKER),
        ],
        storage=StorageConfig(node="pi-node-01"),
    )
    save_config(config)
    return config
