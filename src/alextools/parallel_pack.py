"""Hierarchical parallel tar.gz: compress per-folder at a given depth, then merge with tar (no outer gzip)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def iter_dirs_at_depth(root: Path, depth: int) -> list[Path]:
    root = root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root, topdown=True):
        p = Path(dirpath)
        if p == root:
            rel_parts: tuple[str, ...] = ()
        else:
            rel_parts = p.relative_to(root).parts
        d = len(rel_parts)
        if d == depth:
            found.append(p)
            dirnames[:] = []
        elif d > depth:
            dirnames[:] = []
    return sorted(found)


def leaf_archive_path(work_r0: Path, rel: Path) -> Path:
    parts = rel.parts
    if not parts:
        raise ValueError("empty rel")
    parent, name = parts[:-1], parts[-1]
    return work_r0.joinpath(*parent, f"{name}.tar.gz")


def run_cmd(cmd: list[str], dry_run: bool) -> None:
    if dry_run:
        print("+", " ".join(shlex_quote(c) for c in cmd))
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"Command failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr or r.stdout}"
        )


def shlex_quote(s: str) -> str:
    if not s:
        return "''"
    if all(c.isalnum() or c in "/._-:" for c in s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def tar_dir_to_gz(
    src_dir: Path,
    root: Path,
    out_gz: Path,
    excludes: list[str],
    use_pigz: bool,
    pigz_threads: int,
    dry_run: bool,
) -> None:
    rel = src_dir.relative_to(root)
    parent = src_dir.parent
    base = src_dir.name
    out_gz.parent.mkdir(parents=True, exist_ok=True)
    exclude_args: list[str] = []
    for pat in excludes:
        exclude_args.extend(["--exclude", pat])

    if use_pigz:
        out_gz.parent.mkdir(parents=True, exist_ok=True)
        cmd_tar = ["tar", "cf", "-", "-C", str(parent), base, *exclude_args]
        cmd_pigz = ["pigz", "-p", str(pigz_threads)]
        if dry_run:
            print(
                "+",
                " ".join(shlex_quote(c) for c in cmd_tar),
                "|",
                " ".join(shlex_quote(c) for c in cmd_pigz),
                ">",
                shlex_quote(str(out_gz)),
            )
            return
        p_tar = subprocess.Popen(cmd_tar, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert p_tar.stdout is not None
        with open(out_gz, "wb") as f:
            p_pigz = subprocess.run(
                cmd_pigz,
                stdin=p_tar.stdout,
                stdout=f,
                stderr=subprocess.PIPE,
            )
        p_tar.stdout.close()
        err_tar = p_tar.wait()
        if err_tar != 0:
            err = p_tar.stderr.read().decode() if p_tar.stderr else ""
            raise RuntimeError(f"tar failed: {err}")
        if p_pigz.returncode != 0:
            raise RuntimeError(f"pigz failed: {p_pigz.stderr.decode() if p_pigz.stderr else ''}")
    else:
        cmd = ["tar", "czf", str(out_gz), "-C", str(parent), base, *exclude_args]
        run_cmd(cmd, dry_run)


def _leaf_worker(args: tuple) -> tuple[str, str | None]:
    (
        src_str,
        root_str,
        out_str,
        excludes,
        use_pigz,
        pigz_threads,
        dry_run,
    ) = args
    try:
        tar_dir_to_gz(
            Path(src_str),
            Path(root_str),
            Path(out_str),
            list(excludes),
            use_pigz,
            pigz_threads,
            dry_run,
        )
        return (src_str, None)
    except Exception as e:  # noqa: BLE001
        return (src_str, str(e))


def merge_parent_leaf_tars(
    root: Path,
    parent_rel: Path,
    work_from: Path,
    work_to: Path,
    dry_run: bool,
) -> Path | None:
    src_parent = root / parent_rel
    from_dir = work_from / parent_rel
    if not from_dir.is_dir():
        return None
    members = sorted(from_dir.glob("*.tar.gz"))
    if not members:
        return None
    out = work_to / parent_rel / "bundle.tar"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["tar", "cf", str(out), "-C", str(from_dir)] + [m.name for m in members]
    run_cmd(cmd, dry_run)
    return out


def merge_parent_bundles(
    root: Path,
    parent_rel: Path,
    work_from: Path,
    work_to: Path,
    dry_run: bool,
) -> Path | None:
    src_parent = root / parent_rel
    if not src_parent.is_dir():
        return None
    ch_bundles: list[str] = []
    for ch in sorted(src_parent.iterdir()):
        if not ch.is_dir():
            continue
        b = work_from / parent_rel / ch.name / "bundle.tar"
        if b.is_file():
            ch_bundles.append(f"{ch.name}/bundle.tar")
    if not ch_bundles:
        return None
    out = work_to / parent_rel / "bundle.tar"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = work_from / parent_rel
    cmd = ["tar", "cf", str(out), "-C", str(base)] + ch_bundles
    run_cmd(cmd, dry_run)
    return out


def final_merge_root(
    root: Path,
    work_from: Path,
    output: Path,
    dry_run: bool,
    final_gzip: bool,
) -> None:
    children = sorted([p for p in root.iterdir() if p.is_dir()])
    members: list[str] = []
    for d in children:
        b = work_from / d.name / "bundle.tar"
        if b.is_file():
            members.append(f"{d.name}/bundle.tar")
    loose_files = sorted([p for p in root.iterdir() if p.is_file()])
    output.parent.mkdir(parents=True, exist_ok=True)

    if not members and not loose_files:
        raise RuntimeError("Nothing to put in final archive (empty root?)")

    if loose_files and final_gzip and members:
        raise RuntimeError(
            "Cannot combine top-level directory bundles and loose root files when using --final-gzip; "
            "omit --final-gzip or move files into a subfolder."
        )

    if final_gzip:
        cmd = ["tar", "czf", str(output), "-C", str(work_from), *members]
        if not members and loose_files:
            cmd = ["tar", "czf", str(output), "-C", str(root), *[p.name for p in loose_files]]
        run_cmd(cmd, dry_run)
    else:
        cmd = ["tar", "cf", str(output), "-C", str(work_from), *members]
        run_cmd(cmd, dry_run)
        if loose_files:
            names = [p.name for p in loose_files]
            run_cmd(["tar", "rf", str(output), "-C", str(root), *names], dry_run)


def final_merge_root_flat_r0(
    root: Path,
    work_r0: Path,
    output: Path,
    dry_run: bool,
    final_gzip: bool,
) -> None:
    tars = sorted(work_r0.glob("*.tar.gz"))
    loose_files = sorted([p for p in root.iterdir() if p.is_file()])
    if not tars and not loose_files:
        raise RuntimeError("Nothing to archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    if loose_files and final_gzip and tars:
        raise RuntimeError(
            "Depth 1 with loose root files: use uncompressed final (omit --final-gzip) "
            "so files can be appended with tar rf."
        )
    if final_gzip:
        cmd = ["tar", "czf", str(output), "-C", str(work_r0), *[t.name for t in tars]]
        run_cmd(cmd, dry_run)
    else:
        cmd = ["tar", "cf", str(output), "-C", str(work_r0), *[t.name for t in tars]]
        run_cmd(cmd, dry_run)
        if loose_files:
            names = [p.name for p in loose_files]
            run_cmd(["tar", "rf", str(output), "-C", str(root), *names], dry_run)


def depth_zero_archive(
    root: Path,
    output: Path,
    excludes: list[str],
    dry_run: bool,
    use_pigz: bool,
    pigz_threads: int,
) -> None:
    root = root.resolve()
    parent = root.parent
    base = root.name
    output.parent.mkdir(parents=True, exist_ok=True)
    exclude_args: list[str] = []
    for pat in excludes:
        exclude_args.extend(["--exclude", pat])
    if use_pigz:
        cmd_tar = ["tar", "cf", "-", "-C", str(parent), base, *exclude_args]
        if dry_run:
            print(
                "+",
                " ".join(shlex_quote(c) for c in cmd_tar),
                "| pigz -p",
                str(pigz_threads),
                ">",
                shlex_quote(str(output)),
            )
            return
        with open(output, "wb") as f:
            p_tar = subprocess.Popen(cmd_tar, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert p_tar.stdout is not None
            p_pigz = subprocess.run(
                ["pigz", "-p", str(pigz_threads)],
                stdin=p_tar.stdout,
                stdout=f,
                stderr=subprocess.PIPE,
            )
            p_tar.stdout.close()
            if p_tar.wait() != 0 or p_pigz.returncode != 0:
                raise RuntimeError("depth-0 tar|pigz failed")
    else:
        cmd = ["tar", "czf", str(output), "-C", str(parent), base, *exclude_args]
        run_cmd(cmd, dry_run)


def run_parallel_pack(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    depth: int = args.depth
    jobs: int = max(1, args.jobs)
    dry_run: bool = args.dry_run
    excludes: list[str] = list(args.exclude or [])
    use_pigz: bool = args.pigz
    pigz_threads: int = max(1, args.pigz_threads)
    final_gzip: bool = args.final_gzip

    if use_pigz and shutil.which("pigz") is None:
        print("pigz not found in PATH; install pigz or drop --pigz", file=sys.stderr)
        return 2

    output = Path(args.output).resolve()

    if depth == 0:
        depth_zero_archive(root, output, excludes, dry_run, use_pigz, pigz_threads)
        print(output)
        return 0

    dirs_d = iter_dirs_at_depth(root, depth)
    if not dirs_d:
        print(
            f"No directories at depth {depth} under {root}. "
            "Tree may be shallower than depth, or root is empty.",
            file=sys.stderr,
        )
        return 2

    if args.workdir:
        work_root = Path(args.workdir).resolve()
        work_root.mkdir(parents=True, exist_ok=True)
        cleanup_work = False
    else:
        work_root = Path(tempfile.mkdtemp(prefix="alextools-parallel-pack-"))
        cleanup_work = not args.keep_workdir and not dry_run

    try:
        work_r0 = work_root / "r0"
        work_r0.mkdir(parents=True, exist_ok=True)

        tasks: list[tuple] = []
        for p in dirs_d:
            rel = p.relative_to(root)
            out_gz = leaf_archive_path(work_r0, rel)
            tasks.append(
                (
                    str(p),
                    str(root),
                    str(out_gz),
                    excludes,
                    use_pigz,
                    pigz_threads,
                    dry_run,
                )
            )

        errors: list[str] = []
        if dry_run:
            for t in tasks:
                _leaf_worker(t)
        else:
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                futs = list(ex.map(_leaf_worker, tasks))
            for src, err in futs:
                if err:
                    errors.append(f"{src}: {err}")
            if errors:
                for e in errors:
                    print(e, file=sys.stderr)
                if args.on_error == "fail-fast":
                    return 1

        work_from = work_r0
        round_idx = 1
        for d in range(depth - 1, 0, -1):
            parents = iter_dirs_at_depth(root, d)
            work_to = work_root / f"r{round_idx}"
            work_to.mkdir(parents=True, exist_ok=True)
            for p in parents:
                parent_rel = p.relative_to(root)
                if round_idx == 1:
                    merge_parent_leaf_tars(root, parent_rel, work_from, work_to, dry_run)
                else:
                    merge_parent_bundles(root, parent_rel, work_from, work_to, dry_run)
            work_from = work_to
            round_idx += 1

        if depth == 1:
            final_merge_root_flat_r0(root, work_r0, output, dry_run, final_gzip)
        else:
            final_merge_root(root, work_from, output, dry_run, final_gzip)

        print(output)
        return 0 if not errors else 1
    finally:
        if cleanup_work and not dry_run:
            shutil.rmtree(work_root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Parallel folder-wise gzip tar at a chosen depth, then merge layers with "
            "uncompressed tar (outer gzip optional). Depth 0 = single tar.gz of the whole tree."
        )
    )
    p.add_argument("root", type=str, help="Directory to archive")
    p.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output archive path (.tar or .tar.gz depending on --final-gzip / depth 0)",
    )
    p.add_argument(
        "-d",
        "--depth",
        type=int,
        default=0,
        help="0 = one-shot tar.gz of root; N>=1 = parallel pack each depth-N dir, then merge upward",
    )
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        help="Parallel processes for leaf tar jobs",
    )
    p.add_argument(
        "--workdir",
        type=str,
        default="",
        help="Staging directory (default: temp dir, removed unless --keep-workdir)",
    )
    p.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep staging directory when using default temp workdir",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Extra tar --exclude pattern (repeatable)",
    )
    p.add_argument(
        "--pigz",
        action="store_true",
        help="Use pigz for gzip compression on leaf archives (requires pigz in PATH)",
    )
    p.add_argument(
        "--pigz-threads",
        type=int,
        default=4,
        help="Threads per pigz process when --pigz is set",
    )
    p.add_argument(
        "--final-gzip",
        action="store_true",
        help="Gzip the final archive (depth>=1 only; depth 0 is always compressed)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands instead of running",
    )
    p.add_argument(
        "--on-error",
        choices=("fail-fast", "continue"),
        default="fail-fast",
        help="Leaf job failure handling",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_parallel_pack(args)
