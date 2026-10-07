from __future__ import annotations

import sys


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("NEXUS precisa de um terminal interativo.")
        return 2
    from nexus.app import launch
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
