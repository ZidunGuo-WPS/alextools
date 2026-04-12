# alextools

[简体中文](README_ZH.md)

**alextools** is a small toolbox: **CLI** utilities (`parallel-pack`, `parallel-unpack`) and **Python** helpers (`otsl2html`, `html2otsl` for OTSL/HTML table conversion). Wall-clock benchmark (`tar -czf` vs `parallel-pack`): [docs/parallel_pack_benchmark.md](docs/parallel_pack_benchmark.md).

<details>
<summary>Installation</summary>

```bash
cd alextools
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Installs the `alextools` command and Python package (including `beautifulsoup4` for HTML parsing).

</details>

<details>
<summary>OTSL ↔ HTML (Python API)</summary>

```python
from alextools import otsl2html, html2otsl

html_fragment = otsl2html("<fcel>A<fcel>B<nl><fcel>C<fcel>D<nl>")
otsl = html2otsl("<table><tr><td>A</td><td>B</td></tr></table>")
```

- `otsl2html` returns a `<table>...</table>` fragment (no `<html>` wrapper).
- `html2otsl` reads the first `<table>` in the string; it returns `""` if none is found.

**Verify conversions** (editable install + dev extras for `pytest`, verbose case names):

```bash
pip install -e ".[dev]"
pytest -v
```

OTSL tests assert a strict round-trip: `html2otsl(otsl2html(s)) == s`. Additional tests cover HTML tables without styling.

</details>

<details>
<summary>CLI: <code>parallel-pack</code></summary>

Parallel **gzip** tar for each directory at a chosen **depth** under `root`, then merge layers with **uncompressed** `tar`, and finally one top-level archive. **Depth 0** means a normal single `tar.gz` of the whole tree (no parallelism).

```bash
alextools parallel-pack /path/to/tree -o out.tar -d 2 -j 16
```

- **Depth** counts path segments from `root`: `root` = 0, `root/a` = 1, `root/a/b` = 2.
- **`-d N` (N ≥ 1)**: every directory at depth **N** is archived to its own `.tar.gz` in parallel (`-j` processes). Then each directory at depth N−1 gets a `bundle.tar` of those `.tar.gz` files, and so on, until one final archive under `-o`.
- **`-o`**: output path. Default final layer is **`.tar`** (uncompressed) so you do not gzip already-gzipped blobs. Use **`--final-gzip`** if you want a `.tar.gz` at the end.
- **`--pigz`**: compress leaf archives with `pigz` (install `pigz` on the server). **`--pigz-threads`** sets threads per leaf process.
- **`--exclude PATTERN`**: passed through to `tar` (repeatable), e.g. `.git` or `__pycache__`.
- **`--workdir`**: staging directory (default: temporary, deleted unless **`--keep-workdir`**).
- **`--dry-run`**: print `tar`/`pigz` commands only.

**Extract:** use **`parallel-unpack`** with the **same `-d`**, or manually unpack outer → `bundle.tar` → `.tar.gz` inward.

**Requirements:** `tar` on `PATH`; optional `pigz` for `--pigz`.

</details>

<details>
<summary>CLI: <code>parallel-unpack</code></summary>

Restore a tree produced by `parallel-pack` **with the same `--depth`** you used when packing. By default removes intermediate `bundle.tar` files and gzip-tar `*.tar.gz` created by the tool (files named `.tar.gz` that are not valid gzip-tars are left alone).

```bash
alextools parallel-unpack out.tar -o ./restored -d 2
alextools parallel-pack /path/to/tree -o whole.tar.gz -d 0
alextools parallel-unpack whole.tar.gz -o ./restored -d 0
```

- **`-d`**: required; must match packing depth (`0` = single archive).
- **`--final-gzip` / `--no-final-gzip`**: force outer layer gzip on/off (default: infer from extension).
- **`--keep-archives`**: do not delete `bundle.tar` / `.tar.gz` after extracting them.
- **`--dry-run`**: print planned commands (for depth ≥ 1 the output tree is not read unless you already extracted the outer archive).

</details>

## License

MIT
