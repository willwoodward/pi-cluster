import pytest

from pi_cluster import cli, kube
from pi_cluster.config import load_config, save_config


@pytest.fixture
def playbooks(monkeypatch):
    """Record playbook runs instead of running Ansible."""
    calls = []

    def fake(pb, extra_vars=None, limit=None):
        calls.append((pb, extra_vars))

    monkeypatch.setattr(cli, "run_playbook", fake)
    monkeypatch.setattr(kube, "run_playbook", fake)
    return calls


def run(*argv):
    cli.main(list(argv))


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        run("--help")
    out = capsys.readouterr().out
    for command in ("init", "switch", "kubernetes (kube, k3s)", "deploy", "logs", "reset"):
        assert command in out


def test_up_records_mode(cluster, playbooks):
    run("kubernetes", "up")
    assert [pb for pb, _ in playbooks] == [
        "modes/kubernetes/install.yml",
        "modes/kubernetes/storage.yml",
        "modes/kubernetes/registry.yml",
    ]
    assert load_config().mode == "kubernetes"


def test_up_with_demo_passes_key_and_images(cluster, playbooks):
    run("kube", "up", "--demo")  # alias
    demo = [(pb, ev) for pb, ev in playbooks if pb.endswith("demo.yml")]
    assert demo and demo[0][1]["ssh_private_key"].endswith(".ssh/pi-cluster")
    assert {i["name"] for i in demo[0][1]["images"]} == {"pod-operator", "demo-flask"}


def test_up_refuses_when_another_mode_is_active(cluster, playbooks, monkeypatch, capsys):
    cluster.mode = "something-else"
    save_config(cluster)
    with pytest.raises(SystemExit):
        run("kubernetes", "up")
    assert "cluster switch kubernetes" in capsys.readouterr().err
    assert playbooks == []


def test_down_clears_mode(cluster, playbooks):
    cluster.mode = "kubernetes"
    save_config(cluster)
    run("k3s", "down")
    assert playbooks == [("modes/kubernetes/uninstall.yml", None)]
    assert load_config().mode is None


def test_kube_commands_need_the_mode(cluster, capsys):
    with pytest.raises(SystemExit):
        run("kube", "registry")
    assert "cluster kubernetes up" in capsys.readouterr().err


def test_switch_from_same_mode_is_a_no_op(cluster, playbooks, capsys):
    cluster.mode = "kubernetes"
    save_config(cluster)
    run("switch", "kube")
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


def test_deploy_apps_needs_kubernetes(cluster, playbooks, tmp_path, capsys):
    (tmp_path / "work" / "cluster.toml").write_text('[apps.web]\nimage = "nginx:stable"\n')
    with pytest.raises(SystemExit):
        run("deploy")
    assert "needs the kubernetes mode" in capsys.readouterr().err
    assert playbooks == []


def test_deploy_apps_builds_then_applies(cluster, playbooks, tmp_path):
    cluster.mode = "kubernetes"
    save_config(cluster)
    work = tmp_path / "work"
    (work / "web").mkdir()
    (work / "web" / "Dockerfile").write_text("FROM scratch\n")
    (work / "cluster.toml").write_text(
        '[apps.web]\nbuild = "web"\nport = 8080\n[apps.cache]\nimage = "redis:7"\n'
    )
    run("deploy")
    (build_pb, build_vars), (apply_pb, apply_vars) = playbooks
    assert build_pb == "apps/build.yml"
    assert [i["name"] for i in build_vars["images"]] == ["web"]
    assert apply_pb == "apps/apply.yml"
    by_name = {a["name"]: a for a in apply_vars["apps"]}
    tag = build_vars["images"][0]["tag"]
    assert f"localhost:30007/web:{tag}" in by_name["web"]["manifest"]
    assert by_name["web"]["has_service"] is True
    assert '"redis:7"' in by_name["cache"]["manifest"]
    assert by_name["cache"]["has_service"] is False


def test_undeploy_splits_services_and_apps(cluster, playbooks, tmp_path):
    cluster.mode = "kubernetes"
    save_config(cluster)
    (tmp_path / "work" / "cluster.toml").write_text(
        '[services.agent]\nbinary = "agent"\n[apps.web]\nimage = "nginx"\n'
    )
    run("undeploy")
    assert playbooks == [
        ("services/remove.yml", {"service_names": ["agent"]}),
        ("apps/remove.yml", {"app_names": ["web"]}),
    ]
