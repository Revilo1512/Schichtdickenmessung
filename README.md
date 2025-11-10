This is a student project aimed at providing an application that allows for taking layer thickness measurements, enabling persistent data storage and im-/export and providing a paged view of stored measurements.

This application is a pure python app and uses PyQt6 + PyQt6-Fluent-Widgets for its GUI.
The data storage is created and interfaced using sqlite3. 
The IDS Camera is interfaced using the pyueye library and the corresponding software suite provided by the manufacturer. 
The images are taken and computed using OpenCV python. 
The refractiveindex2 library is used to include the database with the extinctioncoefficient. 
Lastly pytubefix is used to download the introductory video from youtube on first run.

Installation guide:
- Downloads & Install the newest version of the software suite provided by IDS. (Extended version necessary for pyueye support / available on official homepage)
- Download & Install the newest version of uv python package & project manager. (Follow installation instructions on the official homepage)
- Open the folder in IDE of choice or console and clone the repository.
- Run the following commands while in the project directory:
    - uv venv
    - .venv\Scripts\activate
    # Note: You may need to run Set-ExecutionPolicy RemoteSigned -Scope CurrentUser once in PowerShell to allow scripts to run.
    - uv sync
    - uv pip install -e
    - uv run .\src\layer_thickness_app\main.py

- Alternatively use the basic python venv.
    - python -m venv .venv
    - .venv\Scripts\activate
    - pip install -r requirements.txt
    - pip install -e
    - py .\src\layer_thickness_app\main.py