"""pi-cluster: turn a stack of Raspberry Pis into a distributed-systems lab.

The ``cluster`` command (see :mod:`pi_cluster.cli`) discovers the Pis, keeps
them in a known state, layers *modes* such as k3s on top, and deploys your own
binaries as systemd services from a ``cluster.toml``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pi-cluster")  # single source of truth: pyproject.toml
except PackageNotFoundError:  # running from a source checkout that isn't installed
    __version__ = "0.0.0+unknown"
