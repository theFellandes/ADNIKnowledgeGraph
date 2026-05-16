"""Entrypoint so `python -m metrics ...` dispatches to the runner."""

from metrics.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
