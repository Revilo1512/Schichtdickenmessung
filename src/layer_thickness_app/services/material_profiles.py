"""
Material profiles — per-material thresholds and expected ranges.

Each profile is keyed by the (shelf, book, page) tuple that matches the
refractiveindex.info catalog entry used for the measurement. Profiles
override the default plausibility thresholds and give the UI sensible
expected-range and wavelength defaults for the selected material.

Operator notes
--------------
* ``saturation_frac_err`` — capture 10 references with no probe in the
  beam and note the maximum ``saturated_fraction`` observed. Set the
  threshold to a value above that. Clipped pixels invalidate the
  measurement.
* ``gray_mean_min`` — minimum full-image gray mean (ITU-R 601) below
  which the signal is indistinguishable from sensor noise. Capture a
  frame with the laser off and note the gray mean; the threshold
  should sit above this dark-current level.
* ``expected_range_nm`` — the (min, max) thickness range you expect for
  this material. Used to pre-populate the reference-thickness input and
  to hint at the measurable range in messages.
* ``supported_wavelengths_um`` — the wavelengths verified for this
  material against this catalog entry. Used to cross-check the user's
  selection.
* ``shelf`` / ``book`` / ``page`` — the catalog keys. Confirm the exact
  triple on https://refractiveindex.info before populating.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialProfile:
    shelf:                     str
    book:                      str
    page:                      str
    label:                     str
    supported_wavelengths_um:  tuple[float, ...]
    expected_range_nm:         tuple[float, float]
    saturation_frac_err:       float
    gray_mean_min:             float
    notes:                     str = ""


# ---------------------------------------------------------------------------
# Populated profiles. Re-measure these on your own hardware and commit
# the tuned values back here before running a campaign.
# ---------------------------------------------------------------------------
PROFILES: dict[tuple[str, str, str], MaterialProfile] = {
    ("main", "Cu", "Johnson"): MaterialProfile(
        shelf                    = "main",
        book                     = "Cu",
        page                     = "Johnson",
        label                    = "Cu (Johnson & Christy)",
        supported_wavelengths_um = (0.635, 0.532),
        expected_range_nm        = (20.0, 120.0),
        saturation_frac_err      = 0.0050,
        gray_mean_min            = 0.5,
        notes                    = "Tune saturation_frac_err against your beam intensity.",
    ),

    ("main", "Ti", "Rakic-LD"): MaterialProfile(
        shelf                    = "main",
        book                     = "Ti",
        page                     = "Rakic-LD",
        label                    = "Ti (Rakic Lorentz-Drude)",
        supported_wavelengths_um = (0.635, 0.532),
        expected_range_nm        = (15.0, 100.0),
        saturation_frac_err      = 0.0050,
        gray_mean_min            = 0.5,
        notes                    = "Ti absorbs more strongly than Cu at 635 nm.",
    ),
}


def get_profile(shelf: str, book: str, page: str) -> MaterialProfile | None:
    """Look up a MaterialProfile by catalog triple, or return None."""
    return PROFILES.get((shelf, book, page))