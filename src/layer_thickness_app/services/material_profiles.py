"""
Material profiles — per-material thresholds and expected ranges.

Each profile is keyed by the (shelf, book, page) tuple that matches the
refractiveindex.info catalog entry used for the measurement. Profiles
override the default plausibility thresholds and give the UI sensible
expected-range and wavelength defaults for that material.

Operator notes
--------------
* `saturation_warn` — run the laser with no probe in beam, capture 10
  references, note the maximum gray mean observed, and set this value
  to that maximum minus ~10 counts. Don't exceed 250 (hardware saturation
  error kicks in at 254).
* `signal_warn` / `signal_err` — typically leave at the service defaults
  (20 / 10) unless you have a reason to tighten them.
* `expected_range_nm` — the (min, max) thickness range you expect to
  measure for this material. Used to pre-populate the reference-thickness
  input and to hint at the Beer-Lambert measurable range in messages.
* `supported_wavelengths_um` — the wavelengths you've actually verified
  for this material with this catalog entry. Used to cross-check the
  user's selection.
* `shelf` / `book` / `page` — the catalog keys. Confirm the exact triple
  on https://refractiveindex.info before populating.
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
    saturation_warn:           float
    signal_warn:               float
    signal_err:                float
    notes:                     str = ""


# ---------------------------------------------------------------------------
# Populated profiles. The saturation_warn / expected_range_nm values below
# are reasonable starting points — re-measure them on your own hardware
# during the Phase 3 operator session and commit the tuned values here.
# ---------------------------------------------------------------------------
PROFILES: dict[tuple[str, str, str], MaterialProfile] = {
    # Copper — Johnson & Christy is the standard reference for thin-film
    # plasmonic work and the most frequently cited Cu dataset in the
    # literature. Confirm the page key matches your refractiveindex.info
    # selection before running a campaign.
    ("main", "Cu", "Johnson"): MaterialProfile(
        shelf                    = "main",
        book                     = "Cu",
        page                     = "Johnson",
        label                    = "Cu (Johnson & Christy)",
        supported_wavelengths_um = (0.635, 0.532),
        expected_range_nm        = (20.0, 120.0),
        saturation_warn          = 240.0,
        signal_warn              = 20.0,
        signal_err               = 10.0,
        notes                    = "Calibrate saturation_warn against your beam intensity.",
    ),

    # Titanium — Rakić is a broadly-used reference. Adjust the page key
    # if you pick a different catalog entry.
    ("main", "Ti", "Rakic-LD"): MaterialProfile(
        shelf                    = "main",
        book                     = "Ti",
        page                     = "Rakic-LD",
        label                    = "Ti (Rakić Lorentz-Drude)",
        supported_wavelengths_um = (0.635, 0.532),
        expected_range_nm        = (15.0, 100.0),
        saturation_warn          = 240.0,
        signal_warn              = 20.0,
        signal_err               = 10.0,
        notes                    = "Ti absorbs more strongly than Cu at 635 nm.",
    ),
}


def get_profile(shelf: str, book: str, page: str) -> MaterialProfile | None:
    """Look up a MaterialProfile by catalog triple, or return None."""
    return PROFILES.get((shelf, book, page))