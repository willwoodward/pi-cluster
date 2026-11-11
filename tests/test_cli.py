import pytest

from pi_cluster import cli
from pi_cluster.config import load_config, save_config


@pytest.fixture
def playbooks(monkeypatch):
    """Record playbook runs instead of running Ansible."""
    calls = []
    monkeypatch.setattr(
        cli, "run_playbook", lambda pb, extra_vars=None, limit=None: calls.append((pb, extra_vars))
    )
    return calls


def run(*argv):
    cli.main(list(argv))


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        run("--help")
    out = capsys.readouterr().out
    for command in ("init", "create", "switch", "deploy", "logs", "reset", "lights"):
        assert command in out


def test_create_records_mode(cluster, playbooks):
    run("create", "kubernetes")
    assert [pb for pb, _ in playbooks] == [
        "modes/kubernetes/install.yml",
        "modes/kubernetes/storage.yml",
        "modes/kubernetes/registry.yml",
    ]
    assert load_config().mode == "kubernetes"


def test_create_with_demo_passes_key(cluster, playbooks):
    run("create", "kubernetes", "--demo")
    demo = [(pb, ev) for pb, ev in playbooks if pb.endswith("demo.yml")]
    assert demo and demo[0][1]["ssh_private_key"].endswith(".ssh/pi-cluster")


def test_create_refuses_when_another_mode_is_active(cluster, playbooks, monkeypatch, capsys):
    cluster.mode = "something-else"
    save_config(cluster)
    with pytest.raises(SystemExit):
        run("create", "kubernetes")
    assert "cluster switch kubernetes" in capsys.readouterr().err
    assert playbooks == []


def test_destroy_clears_mode(cluster, playbooks):
    cluster.mode = "kubernetes"
    save_config(cluster)
    run("destroy")
    assert playbooks == [("modes/kubernetes/uninstall.yml", None)]
    assert load_config().mode is None


def test_destroy_with_nothing_active(cluster, playbooks, capsys):
    with pytest.raises(SystemExit):
        run("destroy")
    assert "nothing to destroy" in capsys.readouterr().err


def test_switch_from_same_mode_is_a_no_op(cluster, playbooks, capsys):
    cluster.mode = "kubernetes"
    save_config(cluster)
    run("switch", "kubernetes")
    assert playbooks == []
    assert "already active" in capsys.readouterr().out


def test_reset_needs_confirmation_when_not_interactive(cluster, playbooks, capsys):
    with pytest.raises(SystemExit):
        run("reset")
    assert "--yes" in capsys.readouterr().err
    run("reset", "--yes")
    assert playbooks == [("playbooks/reset.yml", None)]


def test_deploy(cluster, playbooks, tmp_path, monkeypatch):
    from tests.test_project import ELF_AARCH64

    (tmp_path / "work" / "agent").write_bytes(ELF_AARCH64)
    (tmp_path / "work" / "cluster.toml").write_text(
        '[services.agent]\nbinary = "agent"\non = "workers"\n'
    )
    run("deploy")
    ((pb, extra),) = playbooks
    assert pb == "services/deploy.yml"
    assert set(extra["services"][0]["hosts"]) == {"pi-node-02", "pi-node-03"}


def test_deploy_runs_build_and_stops_on_failure(cluster, playbooks, tmp_path, capsys):
    (tmp_path / "work" / "cluster.toml").write_text(
        '[build]\ncommand = "exit 3"\n[services.agent]\nbinary = "agent"\n'
    )
    with pytest.raises(SystemExit):
        run("deploy")
    assert "Build failed (exit code 3)" in capsys.readouterr().err
    assert playbooks == []


def test_undeploy_validates_names(cluster, playbooks, capsys):
    with pytest.raises(SystemExit):
        run("undeploy", "bad;name")
    assert playbooks == []
    run("undeploy", "--all")
    assert playbooks == [("services/remove.yml", {"service_names": ["*"]})]


def test_init_refuses_to_overwrite(cluster, capsys):
    with pytest.raises(SystemExit):
        run("init")
    assert "--force" in capsys.readouterr().err


def test_lights_firmware(tmp_path):
    run("lights", "firmware", str(tmp_path))
    assert "neopixel" in (tmp_path / "code.py").read_text()


def test_init_before_flashing_saves_settings(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "ensure_keypair", lambda key: None)
    monkeypatch.setattr(cli, "public_key_text", lambda key: "ssh-ed25519 AAAA test")
    monkeypatch.setattr(cli, "discover", lambda *a, **kw: [])
    with pytest.raises(SystemExit):
        run("init", "--username", "will")
    assert "run `cluster init` again" in capsys.readouterr().err
    assert load_config().ssh.username == "will"

    from pi_cluster.discovery import DiscoveredNode

    monkeypatch.setattr(
        cli,
        "discover",
        lambda *a, **kw: [
            DiscoveredNode("pi-node-01", "10.0.0.1"),
            DiscoveredNode("pi-node-02", "10.0.0.2"),
        ],
    )
    run("init", "--username", "will")  # no --force needed: no nodes yet
    config = load_config()
    assert [n.role for n in config.nodes] == ["control-plane", "worker"]
    assert config.storage.node == "pi-node-01"
