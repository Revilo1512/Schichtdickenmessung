from __future__ import annotations

import cv2
import uuid
import logging
from pathlib import Path
from typing import Any

from PyQt6.QtGui     import QIcon
from PyQt6.QtWidgets import QApplication

from layer_thickness_app.gui.main_window                  import MainWindow
from layer_thickness_app.services.camera_service          import (
    CameraService, FrameCaptureResult,
)
from layer_thickness_app.services.database_service        import DatabaseService
from layer_thickness_app.services.material_service        import MaterialService
from layer_thickness_app.services.material_profiles       import (
    get_profile, MaterialProfile,
)
from layer_thickness_app.services.calculation_service     import CalculationService
from layer_thickness_app.services.plausibility_service    import (
    PlausibilityService, PlausibilityResult, PlausibilitySeverity,
)
from layer_thickness_app.services.calibration_service     import (
    CalibrationService, CalibrationModel,
)
from layer_thickness_app.services.msa_service             import MSAService
from layer_thickness_app.services.export_service          import ExportService
from layer_thickness_app.services.import_service          import ImportService
from layer_thickness_app.config.config                    import AppConfig

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).resolve().parent.parent
ICON_PATH   = BASE_DIR / "gui" / "resources" / "icons" / "app_icon.svg"
DEFAULT_DB  = Path("data") / "measurements.db"


class MainController:
    """Orchestrates services and the main window."""

    def __init__(self, config: AppConfig):
        self.config = config

        # Core services
        self.db_service           = DatabaseService(str(DEFAULT_DB))
        self.export_service       = ExportService(self.db_service)
        self.import_service       = ImportService(self.db_service)
        self.material_service     = MaterialService()
        self.plausibility_service = PlausibilityService()
        self.calculation_service  = CalculationService(
            plausibility_service=self.plausibility_service,
        )
        self.camera_service       = CameraService()
        self.calibration_service  = CalibrationService(db_service=self.db_service)
        self.msa_service          = MSAService()

        # Currently selected MaterialProfile, refreshed on material change.
        self._active_profile: MaterialProfile | None = None

        # View
        self.view = MainWindow(
            db_service          = self.db_service,
            import_service      = self.import_service,
            export_service      = self.export_service,
            camera_service      = self.camera_service,
            calibration_service = self.calibration_service,
            msa_service         = self.msa_service,
            config              = self.config,
        )

        if ICON_PATH.exists():
            self.view.setWindowIcon(QIcon(str(ICON_PATH)))
        else:
            logger.warning("Icon file not found at %s", ICON_PATH)

        self.measurement_page  = self.view.measure_interface
        self.calibration_page  = self.view.calibration_interface
        self.validation_page   = self.view.validation_interface
        self.history_page      = self.view.history_interface

        try:
            self.measurement_page.populate_material_selector(
                self.material_service.get_material_data()
            )
        except Exception as e:
            logger.error("Couldn't load material data: %s", e)

        self._connect_signals()

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def show_window(self):
        self.view.show()

    def shutdown(self) -> None:
        """
        Graceful teardown invoked on QApplication.aboutToQuit. Releases
        the camera and closes the SQLite connection so the WAL/SHM
        sidecar files don't linger.
        """
        try:
            if self.camera_service.get_status().get("connected"):
                self.camera_service.disconnect()
        except Exception as e:
            logger.debug("Camera disconnect on shutdown failed: %s", e)
        try:
            self.db_service.close()
        except Exception as e:
            logger.debug("DB close on shutdown failed: %s", e)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Measure page
        self.measurement_page.calculation_requested.connect(self.on_start_calc)
        self.measurement_page.capture_reference_requested.connect(self.on_take_reference_image)
        self.measurement_page.capture_material_requested.connect(self.on_take_material_image)
        self.measurement_page.reset_requested.connect(self.on_reset_measurement)
        self.measurement_page.config_changed.connect(self._on_measure_config_changed)
        self.measurement_page.material_changed.connect(self._on_material_changed)

        # Calibration page
        try:
            self.calibration_page.calibration_activated.connect(
                self._on_calibration_activated
            )
        except AttributeError as e:
            logger.warning("Calibration page signal not connected: %s", e)

        # Cross-page refresh hooks
        try:
            self.history_page.data_changed.connect(
                self.view.csv_interface._load_filter_suggestions
            )
            self.view.csv_interface.data_changed.connect(
                self.history_page._load_name_suggestions
            )
            self.history_page.data_changed.connect(self.calibration_page.refresh_data)
            self.history_page.data_changed.connect(self.validation_page.refresh_data)
            self.view.csv_interface.data_changed.connect(self.calibration_page.refresh_data)
            self.view.csv_interface.data_changed.connect(self.validation_page.refresh_data)
            logger.info("Connected data_changed signals between pages.")
        except AttributeError as e:
            logger.warning("Could not connect data_changed signals: %s", e)

    def _on_measure_config_changed(self):
        self.measurement_page.set_calculation_enabled(True)

    # ------------------------------------------------------------------
    # MaterialProfile wiring
    # ------------------------------------------------------------------

    def _on_material_changed(self, path: str | None):
        """
        Refresh the per-material plausibility profile and update UI hints
        whenever the operator picks a new material.
        """
        if not path:
            self._active_profile = None
            self.plausibility_service = PlausibilityService()
            self.calculation_service.plausibility = self.plausibility_service
            self.measurement_page.set_profile_caption("")
            self.measurement_page.set_reference_thickness_hint(None, None)
            return

        try:
            shelf, book, page = path.split("/")
        except ValueError:
            logger.debug("Invalid material path: %s", path)
            return

        profile = get_profile(shelf, book, page)
        self._active_profile = profile

        # Build a profile-bound plausibility instance and hand it to the
        # calculation service so the gate uses the right thresholds.
        self.plausibility_service = PlausibilityService(profile=profile)
        self.calculation_service.plausibility = self.plausibility_service

        if profile is None:
            self.measurement_page.set_profile_caption(
                "No material profile -- using default plausibility thresholds."
            )
            self.measurement_page.set_reference_thickness_hint(None, None)
        else:
            self.measurement_page.set_profile_caption(
                f"Profile: {profile.label} "
                f"(sat_frac_warn={profile.saturation_frac_warn:.4f}, "
                f"hotspot_warn={profile.hotspot_warn:.0f}, "
                f"hotspot_err={profile.hotspot_err:.0f})"
            )
            lo, hi = profile.expected_range_nm
            self.measurement_page.set_reference_thickness_hint(lo, hi)

    def _on_calibration_activated(self, calibration_id: int):
        logger.info("New calibration activated: id=%s", calibration_id)
        self.measurement_page.show_info_bar(
            "Calibration Activated",
            f"Calibration #{calibration_id} is now the active correction "
            f"for its material / mode.",
            duration=4000,
        )
        try:
            self.validation_page.refresh_data()
        except Exception as e:
            logger.debug("validation_page refresh after activation failed: %s", e)

    # ------------------------------------------------------------------
    # Capture slots
    # ------------------------------------------------------------------

    def on_reset_measurement(self):
        logger.info("Resetting measurement page.")
        self.measurement_page.reset_all()

    def on_take_reference_image(self):
        if not self._require_camera_connected():
            return
        n_frames = self.measurement_page.get_frame_count()
        self.measurement_page.set_result_text(
            f"Capturing reference ({n_frames} frame{'s' if n_frames > 1 else ''})..."
        )
        QApplication.processEvents()

        capture = self.camera_service.capture_frame(n_frames=n_frames)
        if capture is None:
            self._fail("Capture Error",
                       "Failed to capture reference image. Check camera connection.")
            return

        self.measurement_page.set_capture(capture, "reference")
        self.measurement_page.set_result_text("Result...")
        self.measurement_page.set_calculation_enabled(True)
        self._surface_plausibility(
            self.plausibility_service.check_reference_capture(capture)
        )

    def on_take_material_image(self):
        if not self._require_camera_connected():
            return
        n_frames = self.measurement_page.get_frame_count()
        self.measurement_page.set_result_text(
            f"Capturing sample ({n_frames} frame{'s' if n_frames > 1 else ''})..."
        )
        QApplication.processEvents()

        capture = self.camera_service.capture_frame(n_frames=n_frames)
        if capture is None:
            self._fail("Capture Error",
                       "Failed to capture sample image. Check camera connection.")
            return

        self.measurement_page.set_capture(capture, "material")
        self.measurement_page.set_result_text("Result...")
        self.measurement_page.set_calculation_enabled(True)

        ref_cap = self.measurement_page.reference_capture
        self._surface_plausibility(
            self.plausibility_service.check_sample_capture(capture, ref_cap)
        )

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def on_start_calc(self):
        logger.info("Calculation started.")
        self.measurement_page.set_result_text("Calculating...")
        QApplication.processEvents()

        ui = self.measurement_page.get_measurement_data()

        if ui["ref_capture"] is None or ui["mat_capture"] is None:
            self._fail("Validation Error",
                       "Please capture both reference and sample images first.")
            return
        if not ui["material_path"]:
            self._fail("Validation Error", "No material selected."); return
        if ui["wavelength_um"] is None:
            self._fail("Validation Error", "No wavelength selected."); return

        try:
            shelf, book, page = ui["material_path"].split("/")
        except ValueError:
            self._fail("Internal Error", f"Invalid material path: {ui['material_path']}"); return

        ref_capture: FrameCaptureResult = ui["ref_capture"]
        mat_capture: FrameCaptureResult = ui["mat_capture"]

        logger.info(
            "Calculating | material=%s | lambda=%s um | n=%d/%d frames | "
            "ref_nm=%s | session=%s",
            ui["material_path"], ui["wavelength_um"],
            ref_capture.frames_used, mat_capture.frames_used,
            ui["reference_thickness_nm"], ui["session_tag"],
        )

        try:
            thickness_nm, error_msg, capture_stats = (
                self.calculation_service.calculate_thickness_from_captures(
                    ref_capture, mat_capture, shelf, book, page, ui["wavelength_um"]
                )
            )
        except Exception as e:
            logger.exception("UNHANDLED EXCEPTION in calculation: %s", e)
            self._fail("Unhandled Error", str(e)); return

        if error_msg:
            self._fail("Calculation Error", error_msg); return

        mode = capture_stats.get("Mode", "single")
        corrected_nm = self._apply_active_calibration(
            raw_thickness_nm = thickness_nm,
            shelf=shelf, book=book, page=page,
            wavelength_um = float(ui["wavelength_um"]),
            mode          = mode,
        )
        if corrected_nm is not None:
            capture_stats["ThicknessCorrected"] = round(corrected_nm, 4)

        result_html = self._format_result_html(thickness_nm, corrected_nm)
        self.measurement_page.set_result_text(result_html)
        logger.info(
            "Calculation successful: raw=%.4f nm, corrected=%s",
            thickness_nm,
            f"{corrected_nm:.4f} nm" if corrected_nm is not None else "-",
        )

        if capture_stats.get("plausibility_severity") == PlausibilitySeverity.WARNING.value:
            self.measurement_page.show_info_bar(
                title      = capture_stats.get("plausibility_title", "Warning"),
                content    = capture_stats.get("plausibility_message", ""),
                is_warning = True,
            )

        if ui["save_checked"]:
            self._save_measurement_to_db(
                thickness       = thickness_nm,
                wavelength      = ui["wavelength_um"],
                ref_image       = ref_capture.image,
                mat_image       = mat_capture.image,
                shelf=shelf, book=book, page=page,
                ui_data         = ui,
                capture_stats   = capture_stats,
            )
            self.measurement_page.set_result_text(result_html, append=True)

        self.measurement_page.set_calculation_enabled(False)

    # ------------------------------------------------------------------
    # Calibration helpers
    # ------------------------------------------------------------------

    def _apply_active_calibration(
        self,
        raw_thickness_nm: float,
        shelf: str, book: str, page: str,
        wavelength_um: float, mode: str,
    ) -> float | None:
        try:
            model: CalibrationModel | None = self.calibration_service.load_active(
                shelf=shelf, book=book, page=page,
                wavelength_um=wavelength_um, mode=mode,
            )
        except Exception as e:
            logger.warning("Active-calibration lookup failed: %s", e)
            return None

        if model is None:
            return None

        corrected = model.predict(raw_thickness_nm)

        if not model.is_in_range(raw_thickness_nm):
            logger.warning(
                "Raw value %.3f nm outside calibration range (%.1f-%.1f nm).",
                raw_thickness_nm, model.min_ref_nm, model.max_ref_nm,
            )
            self.measurement_page.show_info_bar(
                "Extrapolation Warning",
                f"Raw value {raw_thickness_nm:.2f} nm is outside the "
                f"calibration range "
                f"({model.min_ref_nm:g}-{model.max_ref_nm:g} nm). "
                f"Corrected value may be unreliable.",
                is_warning=True,
            )
        return corrected

    @staticmethod
    def _format_result_html(raw_nm: float, corrected_nm: float | None) -> str:
        raw_str = f"{raw_nm:.2f} nm"
        if corrected_nm is None:
            return f"<b>{raw_str}</b>"
        corr_str = f"{corrected_nm:.2f} nm"
        return (
            f"<div style='line-height:1.2em;'>"
            f"<span style='font-size:10pt; color: gray;'>Raw&nbsp;{raw_str}</span><br>"
            f"<b>Corrected {corr_str}</b>"
            f"</div>"
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_measurement_to_db(
        self,
        thickness:     float,
        wavelength:    float,
        ref_image,
        mat_image,
        shelf:         str,
        book:          str,
        page:          str,
        ui_data:       dict[str, Any],
        capture_stats: dict[str, Any],
    ):
        logger.info("Saving measurement to database.")
        try:
            name = ui_data["name"] if (ui_data["use_name"] and ui_data["name"]) else "Guest"
            note = ui_data["note"] or None

            ref_img_name = f"ref_{uuid.uuid4()}.png"
            mat_img_name = f"mat_{uuid.uuid4()}.png"

            image_dir = self.db_service.image_dir_path
            cv2.imwrite(str(image_dir / ref_img_name), ref_image)
            cv2.imwrite(str(image_dir / mat_img_name), mat_image)

            db_data: dict[str, Any] = {
                "Name":       name,
                "Layer":      thickness,
                "Wavelength": wavelength,
                "RefImage":   ref_img_name,
                "MatImage":   mat_img_name,
                "Shelf":      shelf,
                "Book":       book,
                "Page":       page,
                "Note":       note,
            }
            db_data.update(capture_stats)

            if ui_data.get("reference_thickness_nm") is not None:
                db_data["ReferenceThickness"] = float(ui_data["reference_thickness_nm"])
            if ui_data.get("session_tag"):
                db_data["SessionTag"] = str(ui_data["session_tag"])
            if ui_data.get("probe"):
                db_data["Probe"] = str(ui_data["probe"])
            if ui_data.get("run_index") is not None:
                db_data["RunIndex"] = int(ui_data["run_index"])

            row_id = self.db_service.save_measurement(db_data)
            if row_id <= 0:
                raise RuntimeError("DatabaseService.save_measurement returned -1")

            logger.info("Measurement saved with ID %s.", row_id)
            self.measurement_page.show_info_bar(
                "Success", f"Measurement saved (ID {row_id}).",
            )

            # Always refresh dependent views after a successful save so
            # filters, suggestions and tables pick up the new row without
            # the user having to re-navigate.
            try:
                self.calibration_page.refresh_data()
            except Exception as e:
                logger.debug("Calibration refresh after save failed: %s", e)
            try:
                self.validation_page.refresh_data()
            except Exception as e:
                logger.debug("Validation refresh after save failed: %s", e)
            try:
                self.history_page.refresh_data()
            except Exception as e:
                logger.debug("History refresh after save failed: %s", e)
            try:
                self.view.csv_interface._load_filter_suggestions()
                self.view.csv_interface.on_update_count()
            except Exception as e:
                logger.debug("CSV refresh after save failed: %s", e)

        except Exception as e:
            logger.exception("Failed to save measurement: %s", e)
            self.measurement_page.show_info_bar(
                "Save Error", "Failed to save measurement.", is_error=True,
            )

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _require_camera_connected(self) -> bool:
        if self.camera_service.get_status()["connected"]:
            return True
        logger.error("Capture requested but camera is not connected.")
        self.measurement_page.show_info_bar(
            "Camera Error",
            "Camera is not connected. Please connect it on the Home page.",
            is_error=True,
        )
        return False

    def _fail(self, title: str, message: str):
        logger.error("%s: %s", title, message)
        self.measurement_page.show_info_bar(title, message, is_error=True)
        self.measurement_page.set_result_text("Error")

    def _surface_plausibility(self, result: PlausibilityResult):
        if result.severity is PlausibilitySeverity.OK:
            return
        self.measurement_page.show_info_bar(
            title      = result.title,
            content    = result.message,
            is_error   = result.is_error,
            is_warning = result.is_warning,
        )