"""Container images: pack a build folder, tag it by content, build it on the cluster.

Images are built on the control-plane (so they're ARM, with nothing to install
on this machine) and pushed to the in-cluster registry. Every node pulls from
it as ``localhost:30007/<name>:<tag>``.

Tags are a hash of the build folder's contents: unchanged code keeps its tag,
so nothing is rebuilt or rolled out, and any change gets a fresh tag, so
Kubernetes always notices the update.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

REGISTRY = "localhost:30007"  # as seen from inside the cluster (every node)
REGISTRY_PORT = 30007

IMAGE_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
ALWAYS_IGNORED = (".git", ".git/**")


@dataclass
class ImageBuild:
    name: str
    context: Path
    tag: str

    @property
    def ref(self) -> str:
        return f"{REGISTRY}/{self.name}:{self.tag}"


def _ignore_patterns(context: Path) -> list[str]:
    patterns = list(ALWAYS_IGNORED)
    dockerignore = context / ".dockerignore"
    if dockerignore.is_file():
        for line in dockerignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("!"):
                line = line.strip("/")
                patterns += [line, f"{line}/**"]
    return patterns


def _ignored(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


def context_files(context: Path) -> list[Path]:
    """Files that go into the build, honouring simple .dockerignore patterns."""
    if not context.is_dir():
        raise FileNotFoundError(f"Build folder {context} doesn't exist.")
    if not (context / "Dockerfile").is_file():
        raise FileNotFoundError(f"No Dockerfile in {context}.")
    patterns = _ignore_patterns(context)
    files = []
    for path in sorted(context.rglob("*")):
        rel = path.relative_to(context).as_posix()
        if path.is_file() and not _ignored(rel, patterns):
            files.append(path)
    return files


def content_tag(context: Path) -> str:
    digest = hashlib.sha256()
    for path in context_files(context):
        digest.update(path.relative_to(context).as_posix().encode() + b"\0")
        digest.update(b"x" if path.stat().st_mode & 0o111 else b"-")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def plan(name: str, context: Path, tag: str | None = None) -> ImageBuild:
    if not IMAGE_NAME_RE.match(name):
        raise ValueError(f"Invalid image name '{name}': use lowercase letters, digits, . _ -")
    if tag is not None and not TAG_RE.match(tag):
        raise ValueError(f"Invalid tag '{tag}'.")
    context = context.resolve()
    return ImageBuild(name=name, context=context, tag=tag or content_tag(context))


def pack(build: ImageBuild, dest_dir: Path) -> Path:
    """Write the build folder to a .tar.gz the playbook unpacks on the control-plane."""
    archive = dest_dir / f"{build.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in context_files(build.context):
            tar.add(path, arcname=path.relative_to(build.context).as_posix())
    return archive


def build_vars(builds: list[ImageBuild], dest_dir: Path, force: bool = False) -> dict:
    return {
        "images": [
            {"name": b.name, "tag": b.tag, "archive": str(pack(b, dest_dir))} for b in builds
        ],
        "force_build": force,
    }
