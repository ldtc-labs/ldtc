"""Sliding windows and bootstrap indices.

A fixed-length per-channel sliding window plus a helper to generate
circular block-bootstrap indices for confidence-interval estimation in
the [`lmeas`][ldtc.lmeas] estimators.

See Also:
    `paper/main.tex`: Methods: Measurement and Attestation Guardrails.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List

import numpy as np


class SlidingWindow:
    """Fixed-length, per-channel sliding window.

    Maintains a `deque` per channel and exposes a dense matrix view when
    the window is full. Useful for streaming estimators that require a
    fixed-size time-by-signal buffer.

    Args:
        capacity: Number of samples to retain per channel.
        channel_order: Ordered list of channel names used for matrix
            columns. Order matters: the matrix columns appear in this
            order, and the column index is what the
            [`PartitionManager`][ldtc.lmeas.partition.PartitionManager]
            stores as a partition member.

    Notes:
        - `append` inserts a new sample dict; missing keys default to
          `0.0`.
        - `get_matrix` returns a `(T, N)` numpy array in `channel_order`.
    """

    def __init__(self, capacity: int, channel_order: List[str]) -> None:
        """Initialize per-channel deques.

        Args:
            capacity: Maximum number of samples to retain per channel.
            channel_order: Ordered list of channel names; matrix columns
                follow this order.
        """
        self.capacity = capacity
        self.order = channel_order
        self.buffers: Dict[str, Deque[float]] = {k: deque(maxlen=capacity) for k in channel_order}

    def append(self, sample: Dict[str, float]) -> None:
        """Append one sample across all channels.

        Args:
            sample: Mapping of channel name to scalar reading. Missing
                channels default to `0.0`.
        """
        for k in self.order:
            self.buffers[k].append(float(sample.get(k, 0.0)))

    def ready(self) -> bool:
        """Return `True` once every channel deque is full."""
        return all(len(self.buffers[k]) == self.capacity for k in self.order)

    def get_matrix(self) -> np.ndarray:
        """Return the current window as a dense `(T, N)` matrix.

        Returns:
            Numpy array of shape `(capacity, len(channel_order))`.

        Raises:
            RuntimeError: If the window is not yet full.
        """
        if not self.ready():
            raise RuntimeError("SlidingWindow not yet full")
        arrs = [np.asarray(self.buffers[k], dtype=float) for k in self.order]
        return np.column_stack(arrs)

    def clear(self) -> None:
        """Drop all buffered samples across every channel."""
        for dq in self.buffers.values():
            dq.clear()


def block_bootstrap_indices(n: int, block: int, draws: int) -> List[np.ndarray]:
    """Circular block-bootstrap indices for time series.

    Generates `draws` index arrays, each of length `n`, by stitching
    together randomly-positioned blocks of length `block` with circular
    wrapping. This preserves short-range temporal dependence in the
    bootstrap samples used by
    [`estimate_L`][ldtc.lmeas.estimators.estimate_L].

    Args:
        n: Length of the time series.
        block: Block length for resampling.
        draws: Number of bootstrap replicates to generate.

    Returns:
        List of index arrays (each of length `n`) representing bootstrap
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
