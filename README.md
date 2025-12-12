# Layer Thickness Measurement Tool (Schichtdickenmessung)

![Project Banner](data/images/banner.png) ## 📖 About The Project

This project, developed as part of **Wahlfachprojekt 2 (WFP2)** at **FH Campus Wien**, provides a standalone graphical application for measuring layer thickness using transmission measurement principles.

The application extends an existing Python code base by providing a user-friendly interface to control an **IDS Industrial Camera**, manage material constants, and perform complex calculations. It ensures data persistence via a local database and offers tools for historical data analysis and export.

## ✨ Key Features

* **Step-by-Step Measurement:** A guided workflow to capture reference and material images and calculate thickness.
* **Hardware Integration:** Direct control of IDS cameras (specifically UI-1240LE-C-HQ) with live preview and connection management.
* **Material Database:** Integrated connection to `refractiveindex.info` to automatically retrieve extinction coefficients for various materials (Shelf/Book/Page).
* **Data Persistence:** Automatic storage of measurement results, timestamps, and parameters using **SQLite**.
* **History & Management:** A dedicated view to filter, sort, and delete past measurements.
* **Import/Export:** Support for exporting measurement data to CSV/ZIP formats for external analysis.
* **Onboarding:** Includes an introductory video (downloaded on first run) to guide new users.

## 🛠️ Tech Stack

* **Language:** Python 3.12+
* **GUI:** PyQt6 & PyQt6-Fluent-Widgets (Windows 11 style components)
* **Computer Vision:** OpenCV (`opencv-python`) for image processing
* **Camera Interface:** `pyueye` & IDS Software Suite
* **Database:** SQLite3
* **Data Sources:** `refractiveindex2` (Material constants), `pytubefix` (Video resources)
* **Dependency Management:** `uv`

## ⚙️ Prerequisites

Before running the application, ensure you have the following hardware and software:

### Hardware
* **IDS Camera:** The system is designed for the **IDS UI-1240LE-C-HQ** (or compatible uEye cameras).

### Software
* **IDS Software Suite:** Download and install the newest version (Extended version necessary for `pyueye` support) from the [official IDS homepage](https://en.ids-imaging.com/downloads.html).
* **Python Package Manager:** This project uses `uv` for fast package management.

## 🚀 Installation

### Option A: Using `uv` (Recommended)

1.  **Install uv:**
    Follow the installation instructions on the [official uv homepage](https://github.com/astral-sh/uv).

2.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Revilo1512/Schichtdickenmessung.git](https://github.com/Revilo1512/Schichtdickenmessung.git)
    cd Schichtdickenmessung
    ```

3.  **Setup and Run:**
    Run the following commands in your terminal (PowerShell/CMD):
    ```powershell
    # Create virtual environment
    uv venv

    # Activate environment
    .venv\Scripts\activate

    # Note: If you get a permission error in PowerShell, run:
    # Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

    # Sync dependencies
    uv sync

    # Install the project in editable mode
    uv pip install -e .

    # Run the application
    uv run src/layer_thickness_app/main.py
    ```

### Option B: Using standard `pip`

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Revilo1512/Schichtdickenmessung.git](https://github.com/Revilo1512/Schichtdickenmessung.git)
    cd Schichtdickenmessung
    ```

2.  **Setup and Run:**
    ```powershell
    # Create virtual environment
    python -m venv .venv

    # Activate environment
    .venv\Scripts\activate

    # Install dependencies
    pip install -r requirements.txt

    # Install project
    pip install -e .

    # Run application
    python src/layer_thickness_app/main.py
    ```

## 🖥️ Usage

1.  **Home:** Upon launching, check the "Camera Status" panel to ensure your IDS camera is connected and recognized.
2.  **Measure:**
    * Select the Material Category (Shelf), Material (Book), and Dataset (Page).
    * Capture a **Reference Image** (light source without sample).
    * Capture a **Material Image** (light source through sample).
    * Click **Calculate** to see the layer thickness result.
3.  **History:** View past measurements. Use the filter options (Date, Name, Material) to find specific records.
4.  **Settings:** Configure theme (Light/Dark) and application defaults.

## 📂 Project Structure

The project is managed with `uv` and follows this structure:

* `src/`: Contains the main application logic (`services`, `controllers`, `gui`).
* `data/`: Stores the SQLite database (`measurements.db`) and captured images.
* `legacy/`: Contains migration scripts and older code iterations.
* `tests/`: Unit tests for calculation and database services.

## 👥 Credits

* **Developer:** Oliver Klager
* **Supervisor:** FH-Prof. Dipl.-Ing. Heimo Hirner
* **Cooperation:** FH-Prof. Christoph Mehofer, BSc
* **Institution:** FH Campus Wien - Computer Science and Digital Communications

---
*Created as part of the CSDCVZ26 curriculum.*