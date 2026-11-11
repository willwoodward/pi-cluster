import textwrap

import pytest

from pi_cluster import project as proj

ELF_AARCH64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + (183).to_bytes(2, "little") + b"\x00" * 40
ELF_X86_64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + (62).to_bytes(2, "little") + b"\x00" * 40


def write_project(tmp_path, body):
    path = tmp_path / "cluster.toml"
    path.write_text(textwrap.dedent(body))
    return path


@pytest.fixture
def example(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "agent").write_bytes(ELF_AARCH64)
    (tmp_path / "bin" / "controller").write_bytes(ELF_AARCH64)
    (tmp_path / "agent.yaml").write_text("x: 1\n")
    path = write_project(
        tmp_path,
        """
        [build]
        command = "make"

        [services.controller]
        binary = "bin/controller"
        on = "control-plane"
        args = ["--listen", "0.0.0.0:8080"]

        [services.agent]
        binary = "bin/agent"
        on = "workers"
        args = ["--controller", "http://{{ control_plane }}:8080", "--name={{node_name}}"]
        env = { RUST_LOG = "info", PORT = 9000 }
        groups = ["kvm"]
        files = ["agent.yaml"]
    """,
    )
    return proj.load_project(path)


def test_load(example, tmp_path):
    assert example.build_command == "make"
    agent = example.services["agent"]
    assert agent.binary == (tmp_path / "bin" / "agent").resolve()
    assert agent.env == {"RUST_LOG": "info", "PORT": "9000"}
    assert agent.unit_name == "pi-cluster-agent.service"
    assert agent.directory == "/opt/pi-cluster/agent"


def test_targets(example, cluster):
    assert [n.name for n in proj.target_nodes(example.services["controller"], cluster)] == [
        "pi-node-01"
    ]
    assert [n.name for n in proj.target_nodes(example.services["agent"], cluster)] == [
        "pi-node-02",
        "pi-node-03",
    ]


def test_explicit_node_list(tmp_path, cluster):
    (tmp_path / "x").write_bytes(b"")
    p = proj.load_project(
        write_project(
            tmp_path,
            """
        [services.x]
        binary = "x"
        on = ["pi-node-03", "pi-node-99"]
    """,
        )
    )
    with pytest.raises(ValueError, match="unknown node 'pi-node-99'"):
        proj.target_nodes(p.services["x"], cluster)


def test_deployment_vars_render_per_node(example, cluster):
    data = proj.deployment_vars([example.services["agent"]], cluster)
    svc = data["services"][0]
    assert svc["user"] == "pi"
    assert set(svc["hosts"]) == {"pi-node-02", "pi-node-03"}
    unit = svc["hosts"]["pi-node-03"]["unit"]
    assert (
        'ExecStart=/opt/pi-cluster/agent/agent "--controller" '
        '"http://192.168.1.11:8080" "--name=pi-node-03"'
    ) in unit
    assert "SupplementaryGroups=kvm" in unit
    assert "User=pi" in unit
    assert svc["hosts"]["pi-node-02"]["env"] == 'RUST_LOG="info"\nPORT="9000"\n'


def test_select(example):
    assert [s.name for s in example.select([])] == ["controller", "agent"]
    assert [s.name for s in example.select(["agent"])] == ["agent"]
    with pytest.raises(ValueError, match="No service called nope"):
        example.select(["nope"])


def test_unknown_placeholder():
    with pytest.raises(ValueError, match="Unknown placeholder"):
        proj.render("{{ nope }}", {"node_name": "a"})


def test_systemd_quoting():
    assert proj.systemd_quote('a "b" $HOME 50%') == r'"a \"b\" $$HOME 50%%"'
    assert proj.systemd_quote("back\\slash") == '"back\\\\slash"'


@pytest.mark.parametrize(
    "body, message",
    [
        ('[services.x]\non = "all"\n', "`binary`"),
        ('[services.X]\nbinary = "b"\n', "lowercase"),
        ('[services.x]\nbinary = "b"\non = "everyone"\n', "`on` must be"),
        ('[services.x]\nbinary = "b"\nport = 1\n', "unknown key"),
        ('[services.x]\nbinary = "b"\nenv = { "1BAD" = "v" }\n', "invalid environment"),
        ('[services.x]\nbinary = "b"\nrestart = "sometimes"\n', "`restart`"),
        ('[services.x]\nbinary = "b"\nargs = "--flag"\n', "list of strings"),
        ('[services.x]\nbinary = "b"\nfiles = ["b"]\n', "both be installed"),
        ('[services.x]\nbinary = "b"\nfiles = ["env"]\n', "both be installed"),
        ("[deploy]\n", "unknown section"),
        ('[build]\ncommand = "make"\n', "at least one"),
        ("not toml", "cluster.toml"),
    ],
)
def test_validation(tmp_path, body, message):
    with pytest.raises(ValueError, match=message):
        proj.load_project(write_project(tmp_path, body))


def test_find_project_searches_parents(tmp_path):
    write_project(tmp_path, '[services.x]\nbinary = "b"\n')
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert proj.find_project(deep) == (tmp_path / "cluster.toml").resolve()


def test_elf_detection(tmp_path):
    (tmp_path / "arm").write_bytes(ELF_AARCH64)
    (tmp_path / "x86").write_bytes(ELF_X86_64)
    (tmp_path / "script").write_text("#!/bin/sh\n")
    assert proj.elf_machine(tmp_path / "arm") == "aarch64"
    assert proj.elf_machine(tmp_path / "x86") == "x86-64"
    assert proj.elf_machine(tmp_path / "script") is None


def test_check_artifacts_rejects_x86(example, tmp_path):
    (tmp_path / "bin" / "agent").write_bytes(ELF_X86_64)
    with pytest.raises(ValueError, match="x86-64 binary"):
        proj.check_artifacts([example.services["agent"]])


def test_check_artifacts_missing_binary(example, tmp_path):
    (tmp_path / "bin" / "agent").unlink()
    with pytest.raises(FileNotFoundError, match="Did the build run"):
        proj.check_artifacts([example.services["agent"]])
