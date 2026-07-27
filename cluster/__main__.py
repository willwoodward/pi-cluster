"""Allow ``python -m cluster`` to behave like the ``cluster`` console script."""

from cluster.cli import main

if __name__ == "__main__":
    main()
