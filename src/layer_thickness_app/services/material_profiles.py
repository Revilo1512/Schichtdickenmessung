"""
Material profiles — per-material thresholds and expected ranges.

Each profile is keyed by the (shelf, book, page) tuple that matches the
refractiveindex.info catalog entry used for the measurement. Profiles
override the default plausibility thresholds and give the UI sensible
expected-range and wavelength defaults for the selected material.

Operator notes
--------------
* ``saturation_frac_warn`` — capture 10 references with no probe in the
  beam, note the maximum ``saturated_fraction`` observed, and set the
  warn threshold to a value just above that. Don't exceed the err
  threshold; clipped pixels in the spot invalidate the measurement.
* ``hotspot_warn`` / ``hotspot_err`` — minimum acceptable spot intensity
  (mean over the top 1 % of pixels). For the thickest layer in your
  campaign, the spot should still sit comfortably above the warn
  threshold; if it drops below ``hotspot_err`` the Beer-Lambert output
  is dominated by sensor noise.
* ``expected_range_nm`` — the (min, max) thickness range you expect for
  this material. Used to pre-populate the reference-thickness input and
  to hint at the Beer-Lambert measurable range in messages.
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
    saturation_frac_warn:      float
    saturation_frac_err:       float
    hotspot_warn:              float
    hotspot_err:               float
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
        saturation_frac_warn     = 0.0010,
        saturation_frac_err      = 0.0050,
        hotspot_warn             = 50.0,
        hotspot_err              = 25.0,
        notes                    = "Tune saturation_frac_warn against your beam intensity.",
    ),

    ("main", "Ti", "Rakic-LD"): MaterialProfile(
        shelf                    = "main",
        book                     = "Ti",
        page                     = "Rakic-LD",
        label                    = "Ti (Rakić Lorentz-Drude)",
        supported_wavelengths_um = (0.635, 0.532),
        expected_range_nm        = (15.0, 100.0),
        saturation_frac_warn     = 0.0010,
        saturation_frac_err      = 0.0050,
        hotspot_warn             = 50.0,
        hotspot_err              = 25.0,
        notes                    = "Ti absorbs more strongly than Cu at 635 nm.",
    ),
}


def get_profile(shelf: str, book: str, page: str) -> MaterialProfile | None:
    """Look up a MaterialProfile by catalog triple, or return None."""
    return PROFILES.get((shelf, book, page))