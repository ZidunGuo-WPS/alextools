"""Unpack archives produced by parallel-pack (same --depth / outer format)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from alextools.parallel_pack import run_cmd, shlex_quote

# Avoid failing as non-root when members are owned by root (e.g. packed on another host).
# Use "-f" <archive> so flags are not mistaken for the file operand (POSIX tar).


def _is_gzip_tar(path: Path) -> bool:
    r = subprocess.run(
        ["tar", "tzf", str(path)],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _outer_extract_cmd(archive: Path, out_root: Path, gzip: bool) -> list[str]:
    cmd = ["tar", "-x", "--no-same-owner", "-f", str(archive), "-C", str(out_root)]
    if gzip:
        cmd.insert(2, "-z")
    return cmd


def _find_bundles(out_root: Path) -> list[Path]:
    return sorted(
        (p for p in out_root.rglob("bundle.tar") if p.is_file()),
        key=lambda p: len(p.relative_to(out_root).parts),
        reverse=True,
    )


def _find_candidate_gzips(out_root: Path) -> list[Path]:
    return sorted(
        (p for p in out_root.rglob("*.tar.gz") if p.is_file()),
        key=lambda p: len(p.relative_to(out_root).parts),
        reverse=True,
    )


def unpack_bundles(out_root: Path, dry_run: bool, remove_archives: bool) -> None:
    if dry_run:
        for b in _find_bundles(out_root):
            parent = b.parent
            print(
                "+ tar -x --no-same-owner -f",
                shlex_quote(str(b)),
                "-C",
                shlex_quote(str(parent)),
                "; rm -f" if remove_archives else "",
                shlex_quote(str(b)) if remove_archives else "",
            )
        return
    while True:
        bundles = _find_bundles(out_root)
        if not bundles:
            break
        for b in bundles:
            parent = b.parent
            run_cmd(
                ["tar", "-x", "--no-same-owner", "-f", str(b), "-C", str(parent)],
                dry_run=False,
            )
            if remove_archives:
                b.unlink(missing_ok=True)


def unpack_leaf_gzips(
    out_root: Path,
    dry_run: bool,
    remove_archives: bool,
) -> None:
    if dry_run:
        for g in _find_candidate_gzips(out_root):
            rm = f"; rm -f {shlex_quote(str(g))}" if remove_archives else ""
            print(
                "+ tar -tzf",
                shlex_quote(str(g)),
                "&& tar -xz --no-same-owner -f",
                shlex_quote(str(g)),
                "-C",
                shlex_quote(str(g.parent)),
                rm,
            )
        return
    while True:
        candidates = _find_candidate_gzips(out_root)
        if not candidates:
            break
        extracted_any = False
        for g in candidates:
            if not _is_gzip_tar(g):
                continue
            run_cmd(
                ["tar", "-xz", "--no-same-owner", "-f", str(g), "-C", str(g.parent)],
                dry_run=False,
            )
            extracted_any = True
            if remove_archives:
                g.unlink(missing_ok=True)
        if not extracted_any:
            break


def run_parallel_unpack(args: argparse.Namespace) -> int:
    archive = Path(args.archive).resolve()
    if not archive.is_file():
        print(f"Not a file: {archive}", file=sys.stderr)
        return 2

    out_root = Path(args.output).resolve()
    depth: int = args.depth
    dry_run: bool = args.dry_run
    remove_archives: bool = args.remove_archives

    if args.final_gzip is not None:
        use_gz = args.final_gzip
    else:
        suf = archive.suffix.lower()
        name = archive.name.lower()
        use_gz = suf == ".gz" or suf == ".tgz" or name.endswith(".tar.gz")

    if depth < 0:
        print("depth must be >= 0", file=sys.stderr)
        return 2

    if depth == 0:
        out_root.mkdir(parents=True, exist_ok=True)
        run_cmd(_outer_extract_cmd(archive, out_root, use_gz), dry_run)
        print(out_root)
        return 0

    if dry_run:
        z = "z" if use_gz else ""
        print(
            "+ tar -x" + z + " --no-same-owner -f",
            shlex_quote(str(archive)),
            "-C",
            shlex_quote(str(out_root)),
        )
        unpack_bundles(out_root, dry_run=True, remove_archives=remove_archives)
        unpack_leaf_gzips(out_root, dry_run=True, remove_archives=remove_archives)
        print(out_root)
        return 0

    out_root.mkdir(parents=True, exist_ok=True)
    run_cmd(_outer_extract_cmd(archive, out_root, use_gz), dry_run=False)

    unpack_bundles(out_root, dry_run=False, remove_archives=remove_archives)
    unpack_leaf_gzips(out_root, dry_run=False, remove_archives=remove_archives)

    if remove_archives:
        for b in list(out_root.rglob("bundle.tar")):
            if b.is_file():
                b.unlink(missing_ok=True)

    print(out_root)
    return 0


def build_unpack_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Unpack archives created by `alextools parallel-pack` with the same "
            "--depth. Removes intermediate bundle.tar and gzip tar .tar.gz by default "
            "(see --keep-archives). Non-tar .tar.gz files are left in place. "
            "Depth 0 = single tar/tar.gz extract."
        )
    )
    p.add_argument("archive", type=str, help="Archive file (.tar or .tar.gz)")
    p.add_argument(
        "-o",
        "--output",
        required=True,
        help="Directory to extract into (created if missing)",
    )
    p.add_argument(
        "-d",
        "--depth",
        type=int,
        required=True,
        help="Must match the depth used when packing (0 = one-shot archive)",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--final-gzip",
        dest="final_gzip",
        action="store_const",
        const=True,
        default=None,
        help="Outermost archive is gzip (.tar.gz); overrides filename guess",
    )
    g.add_argument(
        "--no-final-gzip",
        dest="final_gzip",
        action="store_const",
        const=False,
        default=None,
        help="Outermost archive is uncompressed .tar; overrides filename guess",
    )
    p.add_argument(
        "--keep-archives",
        action="store_true",
        help="Keep bundle.tar and extracted .tar.gz after unpacking",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tar commands only (outer extract not performed for depth>=1)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_unpack_parser().parse_args(argv)
    args.remove_archives = not args.keep_archives
    return run_parallel_unpack(args)
