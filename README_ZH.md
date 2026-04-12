# alextools

日常用的小型命令行工具集。

[English](README.md)

## 安装

```bash
cd alextools
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## 命令

`tar -czf` 与 `parallel-pack` 墙钟耗时对比（实测）：[docs/parallel_pack_benchmark.md](docs/parallel_pack_benchmark.md)。

### `parallel-pack`

<details>
<summary>用法、参数与依赖</summary>

在 `root` 下，先按指定 **深度** 对该深度上的每个子目录**并行**各自打包成 **`.tar.gz`**（也就是 tar 归档后再做 gzip 压缩，俗称 tar.gz）；再用**未压缩**的 `tar` 把这些结果逐层包进更大的 tar，得到最外层归档。**深度 0** 表示整棵树只打一个普通的 `tar.gz`，不做分层并行。

```bash
alextools parallel-pack /path/to/tree -o out.tar -d 2 -j 16
```

- **深度**：从 `root` 起算路径段数：`root` = 0，`root/a` = 1，`root/a/b` = 2。
- **`-d N`（N ≥ 1）**：深度 **N** 上的每个目录各自打成 `.tar.gz`，并行进程数由 `-j` 控制；然后深度 N−1 上的每个目录得到包含这些 `.tar.gz` 的 `bundle.tar`，依此类推，直到 `-o` 指定的最终归档。
- **`-o`**：输出路径。默认最外层是 **`.tar`（不压缩）**，避免对已 gzip 的内容再压一层。若要最外层也是 **`.tar.gz`**，使用 **`--final-gzip`**。
- **`--pigz`**：叶子归档用 `pigz` 压缩（服务器需安装 `pigz`）。**`--pigz-threads`** 指定每个叶子进程的线程数。
- **`--exclude PATTERN`**：原样传给 `tar`（可重复），例如 `.git` 或 `__pycache__`。
- **`--workdir`**：中间工作目录（默认临时目录，除非 **`--keep-workdir`** 否则结束后删除）。
- **`--dry-run`**：只打印将要执行的 `tar`/`pigz` 命令。

**解压：** 使用下面的 **`parallel-unpack`**，**`-d` 与打包时相同**；或手动从最外层起，依次解开 `bundle.tar`、内层 `.tar.gz`。

**依赖：** `PATH` 上需有 `tar`；若使用 **`--pigz`**，需另行安装 `pigz`。

</details>

### `parallel-unpack`

<details>
<summary>用法与参数</summary>

还原由 `parallel-pack` 生成的目录树，**`--depth` 必须与打包时一致**。默认会删除中间的 `bundle.tar` 以及本工具生成的 **gzip 压缩 tar**（`*.tar.gz`）；若某文件虽以 `.tar.gz` 命名但不是合法的 gzip-tar，则不会动它。

```bash
alextools parallel-unpack out.tar -o ./restored -d 2
alextools parallel-pack /path/to/tree -o whole.tar.gz -d 0
alextools parallel-unpack whole.tar.gz -o ./restored -d 0
```

- **`-d`**：必填；须与打包深度一致（`0` 表示单层归档）。
- **`--final-gzip` / `--no-final-gzip`**：强制最外层是否 gzip（默认按扩展名推断）。
- **`--keep-archives`**：解压后不删除 `bundle.tar` / `.tar.gz`。
- **`--dry-run`**：只打印计划执行的命令（深度 ≥ 1 时，若尚未解压最外层归档，则不会读取输出目录树）。

</details>

## 许可证

MIT
