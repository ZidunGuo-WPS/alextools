cd experiment/MNIST
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install numpy matplotlib jupyter ipykernel
python -m ipykernel install --user --name=alextools-mnist --display-name="Python (MNIST)"

命令面板（Ctrl+Shift+P）→ 运行 Python: Select Interpreter。
把/.venv/bin/python的路径粘贴上去
然后就能在.ipynb文件选择内核

分类实验 notebook（`00_setup_and_data.ipynb` … `06_rnn.ipynb`）与本说明同级，均在 `experiment/MNIST/`。若已有 `data/raw/*.gz`，notebook 会优先读本地，不再使用 `./mnist/` 下载目录（见 `mnist_from_raw.py`）。参考实现见子目录 `mnist-classification/*.py`。