"""Read MNIST from ``data/raw/*.gz`` (official idx format).

``torchvision.datasets.MNIST`` expects ``root/MNIST/raw/``, which is a different
layout from a flat ``data/raw/`` folder—so notebooks use this module when your
files are already under ``data/raw``.
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

_DIR = Path(__file__).resolve().parent
DATA_RAW = _DIR / "data" / "raw"

_TRAIN_IMG = "train-images-idx3-ubyte.gz"
_TRAIN_LBL = "train-labels-idx1-ubyte.gz"
_TEST_IMG = "t10k-images-idx3-ubyte.gz"
_TEST_LBL = "t10k-labels-idx1-ubyte.gz"
REQUIRED_FILES = (_TRAIN_IMG, _TRAIN_LBL, _TEST_IMG, _TEST_LBL)


def raw_files_available(raw_dir: Path | None = None) -> bool:
    d = DATA_RAW if raw_dir is None else Path(raw_dir)
    return all((d / n).is_file() for n in REQUIRED_FILES)


def load_images(path: Path) -> np.ndarray:
    with gzip.open(path, "rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        if magic != 2051:
            raise ValueError(f"bad magic {magic}, expected 2051")
        buf = f.read(n * rows * cols)
    return np.frombuffer(buf, dtype=np.uint8).reshape(n, rows, cols)


def load_labels(path: Path) -> np.ndarray:
    with gzip.open(path, "rb") as f:
        magic, n = struct.unpack(">II", f.read(8))
        if magic != 2049:
            raise ValueError(f"bad magic {magic}, expected 2049")
        buf = f.read(n)
    return np.frombuffer(buf, dtype=np.uint8)


def load_all_numpy(raw_dir: Path | None = None):
    """Return train_x, train_y, test_x, test_y (uint8, shapes N×28×28 and (N,))."""
    d = DATA_RAW if raw_dir is None else Path(raw_dir)
    if not raw_files_available(d):
        missing = [n for n in REQUIRED_FILES if not (d / n).is_file()]
        raise FileNotFoundError(f"MNIST raw files missing under {d}: {missing}")
    train_x = load_images(d / _TRAIN_IMG)
    train_y = load_labels(d / _TRAIN_LBL)
    test_x = load_images(d / _TEST_IMG)
    test_y = load_labels(d / _TEST_LBL)
    return train_x, train_y, test_x, test_y


class MNISTNumpyDataset(Dataset):
    """``__getitem__`` matches torchvision ``ToTensor`` MNIST: ``(1,28,28)`` float in ``[0,1]``, long label."""

    def __init__(self, images: np.ndarray, labels: np.ndarray):
        if images.ndim != 3 or images.shape[1:] != (28, 28):
            raise ValueError(f"expected (N, 28, 28), got {images.shape}")
        self.images = images
        self.labels = labels.astype(np.int64, copy=False)

    def __len__(self) -> int:
        return int(self.labels.shape[0])

    def __getitem__(self, idx: int):
        img = self.images[idx]
        x = torch.from_numpy(np.ascontiguousarray(img)).unsqueeze(0).float().div_(255.0)
        y = int(self.labels[idx])
        return x, torch.tensor(y, dtype=torch.long)
