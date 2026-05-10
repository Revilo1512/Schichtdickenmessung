"""
Image statistics for plausibility checks and Beer-Lambert input.

The transmission setup produces a small bright spot in an otherwise dark
frame. The global mean is therefore a poor proxy for both saturation
(clipping in the spot is invisible in the mean) and signal strength
(thicker layers shrink the spot, dragging the mean down even when the
spot itself is well-exposed). These helpers describe the spot directly.

Two pixel statistics are computed:

* ``gray_mean`` / ``gray_p99`` / ``saturated_fraction`` use the standard
  ITU-R BT.601 luminance map. They drive the plausibility gate, which
  cares about whole-frame brightness and clipping irrespective of color.
* ``hotspot_mean`` is computed on the Bayer channel that matches the
  laser wavelength. A 635 nm laser deposits virtually all of its energy
  on red Bayer pixels, a 532 nm laser on green pixels. Mixing in the
  other channels through ITU-R weights would attenuate the actual
  photometric signal by 50-70 %. The hotspot is the top 0.5 % of pixels
  on the matching channel and feeds directly into the Beer-Lambert
  calculation.
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

# OpenCV stores frames in BGR order, hence these channel indices:
_CHANNEL_BLUE  = 0
_CHANNEL_GREEN = 1
_CHANNEL_RED   = 2

# Wavelength bands (in nm) that select a given Bayer channel. The bounds
# follow the rough peak ranges of standard RGB Bayer filters and split
# the supported lasers (532 nm green, 635 nm red) cleanly. Future lasers
# below 500 nm would route through the blue channel.
_BAND_BLUE_MAX_NM:  float = 500.0
_BAND_GREEN_MAX_NM: float = 590.0


@dataclass(frozen=True)
class ImageStats:
    gray_mean:          float
    gray_p99:           float
    hotspot_mean:       float
    saturated_fraction: float


def _wavelength_to_bayer_channel(wavelength_um: float) -> int:
    """
    Map a laser wavelength to the dominant Bayer channel.

    ``wavelength_um`` is given in micrometres for consistency with the
    refractiveindex2 conventions used throughout the codebase.
    """
    nm = wavelength_um * 1000.0
    if nm < _BAND_BLUE_MAX_NM:
        return _CHANNEL_BLUE
    if nm < _BAND_GREEN_MAX_NM:
        return _CHANNEL_GREEN
    return _CHANNEL_RED


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """ITU-R 601 luminance map of a BGR uint8 frame, returned as float64."""
    if frame.ndim == 2:
        return frame.astype(np.float64)
    return (
        0.114 * frame[:, :, 0].astype(np.float64)
        + 0.587 * frame[:, :, 1].astype(np.float64)
        + 0.299 * frame[:, :, 2].astype(np.float64)
    )


def _to_laser_channel(frame: np.ndarray, wavelength_um: float) -> np.ndarray:
    """
    Bayer-channel intensity map of a BGR uint8 frame.

    For grayscale input the same array is returned after a dtype upgrade
    to float64, so callers can apply the same statistics to monochrome
    cameras without a separate code path.
    """
    if frame.ndim == 2:
        return frame.astype(np.float64)
    channel = _wavelength_to_bayer_channel(wavelength_um)
    return frame[:, :, channel].astype(np.float64)


def compute_image_stats(
    frame: np.ndarray,
    wavelength_um: float = 0.635,
) -> ImageStats:
    """
    Per-pixel statistics on a single frame.

    ``gray_mean``, ``gray_p99`` and ``saturated_fraction`` are computed
    on the ITU-R 601 luminance image and feed the plausibility gate.

    ``hotspot_mean`` is the mean over the top ``_HOTSPOT_FRACTION`` of
    pixels on the Bayer channel matching ``wavelength_um`` (0.5 % by
    default). The matching channel is selected via
    :func:`_wavelength_to_bayer_channel`. Using the matching channel
    directly preserves the full photometric signal that would otherwise
    be attenuated by the ITU-R weights.

    The default wavelength corresponds to the red 635 nm laser, which
    is the primary measurement configuration; the green 532 nm laser
    routes the hotspot through the green channel automatically.
    """
    gray  = _to_gray(frame).ravel()
    laser = _to_laser_channel(frame, wavelength_um).ravel()
    n = gray.size
    if n == 0:
        return ImageStats(0.0, 0.0, 0.0, 0.0)

    gray_mean = float(gray.mean())
    gray_p99 = float(np.percentile(gray, 99.0))

    k = max(1, int(round(laser.size * _HOTSPOT_FRACTION)))
    # np.partition pulls the top-k pixels in O(n); avoids a full sort.
    top_k = np.partition(laser, laser.size - k)[laser.size - k:]
    hotspot_mean = float(top_k.mean())

    saturated_fraction = float((gray >= _SATURATION_VALUE).sum()) / float(n)

    return ImageStats(
        gray_mean          = gray_mean,
        gray_p99           = gray_p99,
        hotspot_mean       = hotspot_mean,
        saturated_fraction = saturated_fraction,
    )