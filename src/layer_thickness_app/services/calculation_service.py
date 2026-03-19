import math
import logging
import cv2
import numpy as np
import refractiveindex2 as ri

# Logger für dieses Modul initialisieren
logger = logging.getLogger(__name__)

class CalculationService:
    """
    Used to calculate the thickness of a layer after a measurement has been done.
    """
    
    # --- Magic Numbers (Formel-Konstanten für die Linearisierung) ---
    LINEARIZATION_OFFSET_1 = 0.055
    LINEARIZATION_OFFSET_2 = 1.005
    LINEARIZATION_EXPONENT = 2.4

    def __init__(self):
        pass

    def calculate_thickness(self, 
                            ref_image: np.ndarray, 
                            mat_image: np.ndarray,
                            shelf: str,
                            book: str,
                            page: str,  
                            wavelength_um: float
                            ) -> tuple[float | None, str | None]:
        """
        The main calculation pipeline.
        Takes images and material data, returns (thickness_nm, error_message).
        """
        
        # --- Step 1: Get Extinction Coefficient (k) ---
        try:
            material_path_str = f"{shelf}/{book}/{page}"
            logger.info("Calculating with Material: %s, Wavelength: %sµm", material_path_str, wavelength_um)
            
            material = ri.RefractiveIndexMaterial(shelf, book, page)
            # getExtinctionCoefficient expects wavelength in µm
            k = material.get_extinction_coefficient(wavelength_um) 
            logger.info("Got k value: %s", k)
            
        except Exception as e:
            material_path_str = f"{shelf}/{book}/{page}"
            error_msg = f"Material Error: Could not get k for {material_path_str} at {wavelength_um}µm. ({e})"
            logger.error(error_msg)
            return None, error_msg

        # --- Step 2: Get Absorption Coefficient (alpha) ---
        try:
            alpha_cm = self.calculate_alpha(k, wavelength_um)
            logger.info("Calculated alpha: %s cm⁻¹", alpha_cm)
        except ValueError as e:
            error_msg = f"Math Error: {e}"
            logger.error(error_msg)
            return None, error_msg
            
        # --- Step 3: Process Images to get Mean Grayscale ---
        gw_ref = self.calculate_mean_pixel_value(ref_image, "Reference")
        gw_mat = self.calculate_mean_pixel_value(mat_image, "Material")

        # --- Step 4: Linearize Grayscale Values ---
        lin_mat_intensity = self.linearize_mean_pixel_value(gw_mat)
        lin_ref_intensity = self.linearize_mean_pixel_value(gw_ref)

        # --- Step 5: Calculate Final Thickness ---
        thickness_nm = self.calculate_thickness_from_intensity(
            intensity_transmitted=lin_mat_intensity, 
            intensity_initial=lin_ref_intensity, 
            alpha=alpha_cm
        )
        
        if thickness_nm is None:
            error_msg = "Calculation Error: Invalid values (e.g., Division by zero, check image brightness)."
            logger.error(error_msg)
            return None, error_msg
        
        logger.info("Calculated thickness: %s nm", thickness_nm)
        return thickness_nm, None

    def calculate_mean_pixel_value(self, image: np.ndarray, image_type: str) -> float:
        """Calculates the mean pixel value of a BGR image."""
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_pixel_value = float(np.mean(gray_image))
        logger.info("Mean grayscale value for %s: %s", image_type, mean_pixel_value)
        return mean_pixel_value

    def linearize_mean_pixel_value(self, gw: float) -> float:
        """Linearizes the grayscale value."""
        # Benutzung der Konstanten statt "Magic Numbers"
        gw_norm_lin = (((gw / 255.0) + self.LINEARIZATION_OFFSET_1) / self.LINEARIZATION_OFFSET_2) ** self.LINEARIZATION_EXPONENT
        logger.info("Linearized grayscale value: %s", gw_norm_lin)
        return gw_norm_lin

    def calculate_thickness_from_intensity(self, intensity_transmitted: float, intensity_initial: float, alpha: float) -> float | None:
        """
        Calculates thickness based on the Beer-Lambert law.
        intensity_transmitted = Intensity of light passing through material (Material Image)
        intensity_initial     = Initial intensity of light source (Reference Image)
        alpha                 = Absorption coefficient in cm⁻¹
        """
        # Verhindert Division durch 0 und fehlerhafte Logarithmus-Berechnungen
        if intensity_transmitted <= 0 or intensity_initial <= 0 or alpha == 0:
            logger.error("Invalid values for calculation. Intensities must be > 0 and alpha != 0.")
            return None
        
        try:
            # Beer-Lambert: ln(I / I0) = -alpha * x
            x_cm = math.log(intensity_transmitted / intensity_initial) * (1 / -alpha)
            logger.info("Calculated sample thickness in cm: %s", x_cm)
            
            # Umrechnung in Nanometer
            x_nm = x_cm * 1e7
            return x_nm
            
        except Exception as e:
            logger.error("Error during thickness calculation: %s", e)
            return None

    def calculate_alpha(self, k: float, lambda_um: float) -> float:
        """
        Calculates the absorption coefficient α [cm⁻¹] from:
        - k: Extinction coefficient (dimensionless)
        - lambda_um: Wavelength in micrometers [µm]
        """
        if lambda_um <= 0:
            raise ValueError("Wavelength must be greater than 0.")
        
        # 1 µm = 10⁻⁴ cm
        lambda_cm = lambda_um * 1e-4
        
        # α = 4πk / λ
        alpha = (4 * math.pi * k) / lambda_cm
        
        return alpha