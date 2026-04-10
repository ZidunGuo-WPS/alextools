"""alextools CLI entrypoint."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: alextools <command> [options]\n\n"
            "Commands:\n"
            "  parallel-pack    Depth-aware parallel tar then merge (see: alextools parallel-pack -h)\n"
            "  parallel-unpack  Restore tree packed with parallel-pack (see: alextools parallel-unpack -h)",
            file=sys.stderr,
        )
        return 0 if argv and argv[0] in ("-h", "--help") else 2

    cmd = argv[0]
    rest = argv[1:]
    if cmd == "parallel-pack":
        from alextools.parallel_pack import main as pack_main

        return pack_main(rest)
    if cmd == "parallel-unpack":
        from alextools.parallel_unpack import main as unpack_main

        return unpack_main(rest)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2
