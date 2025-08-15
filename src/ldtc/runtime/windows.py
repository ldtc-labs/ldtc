from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List
import numpy as np


class SlidingWindow:
    """
    Maintains a fixed-length sliding window for named channels.

    - append(sample_dict) with keys -> float
    - get_matrix(order) returns ndarray shape (T, N) in `order`
    """

    def __init__(self, capacity: int, channel_order: List[str]) -> None:
        self.capacity = capacity
        self.order = channel_order
        self.buffers: Dict[str, Deque[float]] = {
            k: deque(maxlen=capacity) for k in channel_order
        }

    def append(self, sample: Dict[str, float]) -> None:
        for k in self.order:
            self.buffers[k].append(float(sample.get(k, 0.0)))

    def ready(self) -> bool:
        return all(len(self.buffers[k]) == self.capacity for k in self.order)

    def get_matrix(self) -> np.ndarray:
        if not self.ready():
            raise RuntimeError("SlidingWindow not yet full")
        arrs = [np.asarray(self.buffers[k], dtype=float) for k in self.order]
        return np.column_stack(arrs)

    def clear(self) -> None:
        for dq in self.buffers.values():
            dq.clear()


def block_bootstrap_indices(n: int, block: int, draws: int) -> List[np.ndarray]:
    """
    Simple circular block bootstrap indices for time series.
    Returns list of index arrays of length n.
    """
    idxs: List[np.ndarray] = []
    for _ in range(draws):
        i = 0
        out = []
        while i < n:
            start = np.random.randint(0, n)
            take = min(block, n - i)
            sel = (np.arange(take) + start) % n
            out.append(sel)
            i += take
        idxs.append(np.concatenate(out))
    return idxs
