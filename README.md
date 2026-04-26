# Layer Thickness Measurement Tool

A standalone GUI application for measuring thin-film layer thickness via
transmission photometry. Captures reference and sample images from an
IDS industrial camera, computes thickness via the Beer–Lambert law, and
provides calibration and Measurement System Analysis (MSA Type 1)
workflows for traceable, capability-verified results.

## Features

### Measurement
- Guided two-image capture workflow (reference + sample).
- **Single-frame** mode for fast measurements and **multi-frame**
  averaging mode (configurable, default 30 frames) with per-frame
  outlier rejection (σ-clipping) for noise reduction.
- Live grayscale readout while capturing.
- Live plausibility checks: saturation warnings, low-signal warnings,
  ref-vs-sample sanity (sample must be darker), per-material expected
  thickness ranges.
- Optional **batch mode**: hold the reference fixed, auto-increment the
  run index, capture *N* repeats per probe for MSA studies.

### Calibration
- Fit a linear correction model (`y = β₁·x + β₀`) from any subset of
  past calibration measurements.
- Per-row train/test/ignore assignment with quick actions
  (all-train, random 70/30 split, hold-out by reference thickness).
- Reports R², slope, intercept, and a before/after metrics panel
  showing bias / MAE / RMSE / max-|err| on the held-out test set.
- Save & activate the model so subsequent measurements are
  automatically corrected.

### Validation (MSA Type 1)
- Repeat-measurements capability study per probe.
- Computes Cg and Cgk per Minitab/ISO 22514-7 conventions
  (default K=20, L=6, capable threshold = 1.33).
- Side-by-side raw vs corrected reports when a calibration is active —
  quantifies whether the correction actually improved capability.
- Exports a complete study (summary + CSVs) as a timestamped ZIP.

### Material catalog
- Connected to **refractiveindex.info** via the `refractiveindex2`
  package — pulls extinction coefficients for any catalog
  shelf / book / page.
- Material profiles override default plausibility thresholds and
  expected-range hints for known materials (Cu Johnson & Christy,
  Ti Rakić-LD shipped by default; easy to add more).

### Data management
- Local SQLite database with measurements, calibration models, and
  schema migrations on startup.
- Filterable history with pagination and per-row delete.
- Import / export the entire database (or a filtered subset) to a
  self-contained ZIP archive (CSV + image files) for sharing or
  long-term archival.

### UI
- PyQt6 + qfluentwidgets (Windows 11 / Fluent design language).
- Light, dark, and Auto themes (Auto follows the OS preference on
  Windows).
- Centralised theme module — all colors, borders, and font scales
  live in one file (`gui/theme.py`).

## Tech Stack

| Layer | Library |
|---|---|
| Language | Python 3.12+ |
| GUI | PyQt6, [PyQt6-Fluent-Widgets](https://qfluentwidgets.com/) |
| Numerics | NumPy |
| Image processing | OpenCV (`opencv-python`) |
| Camera | `pyueye` + IDS Software Suite |
| Material data | `refractiveindex2`, PyYAML |
| Persistence | SQLite (stdlib `sqlite3`) |
| Onboarding video | `pytubefix` |
| Package manager | [`uv`](https://github.com/astral-sh/uv) (recommended) |

## Prerequisites

### Hardware
- IDS uEye industrial camera. Reference hardware: **IDS UI-1240LE-C-HQ**.
  Other uEye models supported by `pyueye` should work without code changes.
- Mounted transmission optics with a stable, uniform light source
  (laser diode at 532 nm and/or 635 nm).

### Software
1. **IDS Software Suite (Extended)** — required by `pyueye`.
   Download from the
   [official IDS site](https://en.ids-imaging.com/downloads.html).
2. **Python 3.12 or later**.
3. Recommended: **`uv`** for dependency management
   (see [uv installation](https://github.com/astral-sh/uv)).

## Installation

### Option A — `uv` (recommended)

```powershell
git clone https://github.com/Revilo1512/Schichtdickenmessung.git
cd Schichtdickenmessung

uv venv
.venv\Scripts\activate

uv sync
uv pip install -e .

uv run src/layer_thickness_app/main.py
```

If PowerShell refuses to run the activate script:
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Option B — `pip`

```powershell
git clone https://github.com/Revilo1512/Schichtdickenmessung.git
cd Schichtdickenmessung

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
pip install -e .

python src/layer_thickness_app/main.py
```

## Quick Start

1. Launch the app. The Home page auto-detects the camera; if it doesn't
   appear, click **Refresh List** then **Connect**.
2. Go to **Measure**.
   - Select Shelf → Book → Page (e.g. `main / Cu / Johnson`).
   - Pick the wavelength (532 nm or 635 nm) matching your light source.
   - Choose the frame count (30 is a good default for noisy hardware).
   - Click **Take Reference Image** without the sample in the beam.
   - Place the sample in the beam and click **Take Material Image**.
   - Click **Calculate**. The result and (if a calibration is active)
     the corrected value appear in the result panel.
3. Optional flows:
   - **History**: filter, paginate, delete past measurements.
   - **Calibration**: build a linear correction model from past
     measurements that have a known reference thickness.
   - **Validation**: run a Type 1 MSA study to verify capability.
   - **Ex-/Import**: export a filtered subset to a ZIP, or re-import
     a ZIP from another machine.
4. **Settings**: theme, window size.

### Keyboard shortcuts (Measure page)
| Key | Action |
|---|---|
| `R` | Capture reference image |
| `S` | Capture sample image |
| `Enter` | Run calculation |
| `Ctrl+S` | Toggle "save measurement" |

## Project Structure

```
Schichtdickenmessung/
├── data/
│   ├── measurements.db          # SQLite database (created on first run)
│   ├── images/                  # captured reference/sample PNGs
│   └── banner.png
├── src/
│   └── layer_thickness_app/
│       ├── main.py                       # entry point, splash, theme bootstrap
│       ├── config/
│       │   └── config.py                 # AppConfig, persisted settings
│       ├── controller/
│       │   └── main_controller.py        # wires services ↔ widgets
│       ├── gui/
│       │   ├── theme.py                  # central style tokens & helpers
│       │   ├── main_window.py            # FluentWindow + navigation
│       │   ├── resources/
│       │   │   ├── app_icon.svg
│       │   │   ├── light_theme.qss
│       │   │   ├── dark_theme.qss
│       │   │   ├── measurement_device.jpg
│       │   │   └── tutorial.mp4          # optional, fetched on first run
│       │   └── widgets/
│       │       ├── home_page.py
│       │       ├── measure_page.py
│       │       ├── history_page.py
│       │       ├── calibration_page.py
│       │       ├── validation_page.py
│       │       ├── csv_page.py
│       │       ├── help_page.py
│       │       └── settings_page.py
│       └── services/
│           ├── camera_service.py         # frame capture + outlier rejection
│           ├── calculation_service.py    # Beer–Lambert + sRGB linearisation
│           ├── plausibility_service.py   # saturation / signal / range checks
│           ├── calibration_service.py    # linear-regression correction model
│           ├── msa_service.py            # Cg / Cgk capability indices
│           ├── database_service.py       # SQLite schema + CRUD
│           ├── material_service.py       # refractiveindex.info catalog loader
│           ├── material_profiles.py      # per-material thresholds (Cu, Ti)
│           ├── import_service.py         # ZIP → DB
│           ├── export_service.py         # DB → ZIP
│           └── report_service.py         # MSA study export (CSV + summary)
├── pyproject.toml
├── requirements.txt
└── README.md
```

### Architecture

The application follows a service-oriented MVC-style layout:

- **Services** are stateless or self-contained business-logic units —
  they can be unit-tested without any Qt dependency. Examples:
  `CalculationService` runs the Beer-Lambert math, `MSAService`
  computes Cg/Cgk.
- **Widgets** (`gui/widgets/`) are pure UI: they emit signals and expose
  setter methods, but never call services directly.
- **Controller** wires the two together: it owns the service instances,
  connects widget signals to service calls, and pushes results back
  into widget setters. Material-profile changes are propagated by the
  controller, which rebuilds a profile-bound `PlausibilityService`
  on each material switch.
- **Theme** (`gui/theme.py`) centralises every color, border, and font
  decision. UI files import `card_style()`, `status_label_style()`,
  `quality_color()`, etc. — no inline hex literals.

### Database schema (overview)

The `database_service` owns three tables:

| Table | Purpose |
|---|---|
| `measurements` | one row per captured measurement (raw + corrected layer values, gray statistics, frame counts, material catalog triple, optional reference thickness, session tag, probe, run index) |
| `calibrations` | saved linear correction models (slope, intercept, R², fitted range, material/wavelength/mode, active flag) |
| `msa_runs` | (optional, for archival) saved Type 1 MSA reports |

Schema migrations run automatically at startup — the service inspects
existing columns and adds new ones in place. No manual migration step.

### Configuration constants

Tunable thresholds live in `config/config.py` as `AppConfig` class
attributes:

| Constant | Default | Purpose |
|---|---|---|
| `FRAME_COUNT_DEFAULT` | 30 | Default frames per multi-frame capture |
| `PLAUSIBILITY_SAT_ERR` | 254.0 | Above this gray mean: saturation error |
| `PLAUSIBILITY_SAT_WARN` | 240.0 | Above this: saturation warning |
| `PLAUSIBILITY_SIG_ERR` | 10.0 | Below this: signal-too-low error |
| `PLAUSIBILITY_SIG_WARN` | 20.0 | Below this: signal-low warning |
| `WAVELENGTHS` | 635 nm, 532 nm | Selectable wavelengths |
| `DB_PATH` | `data/measurements.db` | SQLite file location |

## Logging

The app writes a rotating log file `app_log.txt` in the working
directory (1 MB × 5 backups) and mirrors `INFO`-level events to stdout.
Qt's noisy "QFont::setPointSize: Point size <= 0" warning is filtered
out at the Qt message handler.

## Building a Windows executable (optional)

The repo does not ship a build script, but PyInstaller works out of the
box once dependencies are installed:

```powershell
pyinstaller `
  --name "LayerThicknessTool" `
  --windowed `
  --icon src/layer_thickness_app/gui/resources/app_icon.ico `
  --add-data "src/layer_thickness_app/gui/resources;layer_thickness_app/gui/resources" `
  src/layer_thickness_app/main.py
```

To convert the SVG icon to a multi-resolution `.ico`:
```powershell
magick app_icon.svg -define icon:auto-resize=256,128,64,48,32,16 app_icon.ico
```

## Contributing

Issues and pull requests are welcome. When opening a PR:
- Keep service code Qt-free.
- Route any new colors / borders / fonts through `gui/theme.py`.
- Add new schema columns by extending `_ensure_schema()` in
  `database_service.py` rather than editing the `CREATE TABLE`
  statements directly.

## License

See `LICENSE` for details.
