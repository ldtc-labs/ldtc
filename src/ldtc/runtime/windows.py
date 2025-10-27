"""Runtime: Sliding windows and bootstrap indices.

Provides a fixed-length per-channel window and helper to generate circular
block-bootstrap indices for CI estimation.

See Also:
    paper/main.tex — Methods: Measurement & Attestation Guardrails.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List
import numpy as np


class SlidingWindow:
    """Fixed-length, per-channel sliding window.

    Maintains a deque per channel and exposes a dense matrix view when the
    window is full. Useful for streaming estimators that require a fixed-size
    time-by-signal buffer.

    Args:
        capacity: Number of samples to retain per channel.
        channel_order: Ordered list of channel names used for matrix columns.

    Notes:
        - ``append`` inserts a new sample dict; missing keys default to 0.0.
        - ``get_matrix`` returns a ``(T, N)`` numpy array in ``channel_order``.
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
    """Circular block-bootstrap indices for time series.

    Args:
        n: Length of the time series.
        block: Block length for resampling.
        draws: Number of bootstrap replicates to generate.

    Returns:
        List of index arrays (each of length ``n``) representing bootstrap
        samples with circular wrapping at boundaries.
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
