import tarfile

import pytest

from pi_cluster import images


@pytest.fixture
def context(tmp_path):
    ctx = tmp_path / "web"
    ctx.mkdir()
    (ctx / "Dockerfile").write_text("FROM scratch\nCOPY app.py /\n")
    (ctx / "app.py").write_text("print('hi')\n")
    (ctx / ".git").mkdir()
    (ctx / ".git" / "HEAD").write_text("ref\n")
    (ctx / "node_modules").mkdir()
    (ctx / "node_modules" / "big.js").write_text("x\n")
    (ctx / ".dockerignore").write_text("# comment\nnode_modules\n")
    return ctx


def test_files_skip_git_and_dockerignore(context):
    names = [p.relative_to(context).as_posix() for p in images.context_files(context)]
    assert names == [".dockerignore", "Dockerfile", "app.py"]


def test_tag_follows_content(context):
    first = images.content_tag(context)
    assert first == images.content_tag(context)  # stable
    (context / "node_modules" / "big.js").write_text("changed\n")
    assert images.content_tag(context) == first  # ignored files don't count
    (context / "app.py").write_text("print('bye')\n")
    assert images.content_tag(context) != first


def test_plan_and_pack(context, tmp_path):
    build = images.plan("web", context)
    assert build.ref == f"localhost:30007/web:{build.tag}"
    archive = images.pack(build, tmp_path)
    with tarfile.open(archive) as tar:
        assert sorted(tar.getnames()) == [".dockerignore", "Dockerfile", "app.py"]


def test_explicit_tag_and_validation(context):
    assert images.plan("web", context, "v1").tag == "v1"
    with pytest.raises(ValueError, match="Invalid image name"):
        images.plan("Web!", context)
    with pytest.raises(ValueError, match="Invalid tag"):
        images.plan("web", context, "bad tag")


def test_needs_a_dockerfile(tmp_path):
    with pytest.raises(FileNotFoundError, match="No Dockerfile"):
        images.content_tag(tmp_path)
