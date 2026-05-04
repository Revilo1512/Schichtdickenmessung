"""
Image statistics for plausibility checks.

The transmission setup produces a small bright spot in an otherwise dark
frame. The global mean is therefore a poor proxy for both saturation
(clipping in the spot is invisible in the mean) and signal strength
(thicker layers shrink the spot, dragging the mean down even when the
spot itself is well-exposed). These helpers describe the spot directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Top fraction of pixels treated as "the laser spot" for hotspot statistics.
# Tight enough to stay inside the spot for very thick layers, large enough
# to average over local sensor noise.
_HOTSPOT_FRACTION: float = 0.005

# Pixel value at and above which a pixel is considered clipped.
_SATURATION_VALUE: int = 254


@dataclass(frozen=True)
class ImageStats:
    gray_mean:          float
    gray_p99:           float
    hotspot_mean:       float
    saturated_fraction: float


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """ITU-R 601 luminance map of a BGR uint8 frame, returned as float64."""
    if frame.ndim == 2:
        return frame.astype(np.float64)
    return (
        0.114 * frame[:, :, 0].astype(np.float64)
        + 0.587 * frame[:, :, 1].astype(np.float64)
        + 0.299 * frame[:, :, 2].astype(np.float64)
    )


def compute_image_stats(frame: np.ndarray) -> ImageStats:
    """
    Per-pixel statistics on a single frame.

    ``hotspot_mean`` is the mean over the top ``_HOTSPOT_FRACTION`` of
    pixels by luminance (0.5 % by default) — a robust estimate of the
    laser spot intensity that does not require locating the spot.
    ``saturated_fraction`` is the fraction of pixels at or above
    ``_SATURATION_VALUE`` and detects clipping even when most of the
    frame is dark.
    """
    gray = _to_gray(frame).ravel()
    n = gray.size
    if n == 0:
        return ImageStats(0.0, 0.0, 0.0, 0.0)

    gray_mean = float(gray.mean())
    gray_p99 = float(np.percentile(gray, 99.0))

    k = max(1, int(round(n * _HOTSPOT_FRACTION)))
    # np.partition pulls the top-k pixels in O(n); avoids a full sort.
    top_k = np.partition(gray, n - k)[n - k:]
    hotspot_mean = float(top_k.mean())

    saturated_fraction = float((gray >= _SATURATION_VALUE).sum()) / float(n)

    return ImageStats(
        gray_mean          = gray_mean,
        gray_p99           = gray_p99,
        hotspot_mean       = hotspot_mean,
        saturated_fraction = saturated_fraction,
    )