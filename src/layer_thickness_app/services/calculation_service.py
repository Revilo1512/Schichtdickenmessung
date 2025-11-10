import math
import cv2
import numpy as np
import refractiveindex2 as ri
from typing import Tuple, Optional

class CalculationService:
    """
    Used to calculate the thickness of layer after a measurement has been done.
    """
    def __init__(self):
        pass

    def calculate_thickness(self, 
                            ref_image: np.ndarray, 
                            mat_image: np.ndarray,
                            shelf: str,
                            book: str,
                            page: str,  
                            wavelength_um: float
                            ) -> Tuple[Optional[float], Optional[str]]:
        """
        The main calculation pipeline.
        Takes images and material data, returns (thickness_nm, error_message).
        """
        
        # --- Step 1: Get Extinction Coefficient (k) ---
        try:
            material_path_str = f"{shelf}/{book}/{page}"
            print(f"Calculating with Material: {material_path_str}, Wavelength: {wavelength_um}µm")
            material = ri.RefractiveIndexMaterial(shelf, book, page)
            # getExtinctionCoefficient expects wavelength in µm
            k = material.get_extinction_coefficient(wavelength_um) 
            print(f"Got k value: {k}")
        except Exception as e:
            material_path_str = f"{shelf}/{book}/{page}"
            error_msg = f"Material Error: Could not get k for {material_path_str} at {wavelength_um}µm. ({e})"
            print(error_msg)
            return None, error_msg

        # --- Step 2: Get Absorption Coefficient (alpha) ---
        try:
            alpha_cm = self.berechne_alpha(k, wavelength_um)
            print(f"Calculated alpha: {alpha_cm} cm⁻¹")
        except ValueError as e:
            error_msg = f"Math Error: {e}"
            print(error_msg)
            return None, error_msg
            
        # --- Step 3: Process Images to get Mean Grayscale ---
        gw_ref = self.calculate_mean_pixel_value(ref_image, "Reference")
        gw_mat = self.calculate_mean_pixel_value(mat_image, "Material")

        # --- Step 4: Linearize Grayscale Values ---
        # I = material image (light passing through material)
        # I1 = reference image (light source)
        lin_mat_I = self.linearize_mean_pixel_value(gw_mat)
        lin_ref_I1 = self.linearize_mean_pixel_value(gw_ref)

        # --- Step 5: Calculate Final Thickness ---
        thickness_nm = self.berechne_x(I=lin_mat_I, I1=lin_ref_I1, f=alpha_cm)
        
        if thickness_nm is None:
            error_msg = "Calculation Error: Division by zero (check image brightness)."
            print(error_msg)
            return None, error_msg
        
        print(f"Calculated thickness: {thickness_nm} nm")
        return thickness_nm, None

    def calculate_mean_pixel_value(self, image: np.ndarray, bildcounter: str) -> float:
        """Calculates the mean pixel value of a BGR image."""
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_pixel_value = np.mean(gray_image)
        print(f"Mean grayscale value for {bildcounter}: {mean_pixel_value}")
        return mean_pixel_value

    def linearize_mean_pixel_value(self, GW: float) -> float:
        """Linearizes the grayscale value."""
        GWnorm_lin = (((GW / 255.0) + 0.055) / 1.005) ** 2.4
        print(f"Linearized grayscale value: {GWnorm_lin}")
        return GWnorm_lin

    def berechne_x(self, I: float, I1: float, f: float) -> Optional[float]:
        """
        Calculates thickness 'x' based on Beer-Lambert law.
        I1 = Transmitted intensity (material image)
        I = Initial intensity (reference image)
        f = Absorption coefficient (alpha) in cm⁻¹
        """
        if I == 0 or I1 == 0 or f == 0:
            print("Invalid values for calculation. I, I1, and f must be > 0.")
            return None
        
        try:
            x_cm = math.log(I / I1) * (1 / -f)
            print("Die Dicke der Probe ist:", x_cm, "cm")
            x_nm = x_cm * 1e7
            return x_nm
        except Exception as e:
            print(f"Error during thickness calculation: {e}")
            return None

    def berechne_alpha(self, k: float, lambda_um: float) -> float:
        """
        Berechnet den Absorptionskoeffizienten α [cm⁻¹] aus:
        - k: Extinktionskoeffizient (dimensionslos)
        - lambda_um: Wellenlänge in Mikrometer [µm]

        Rückgabe:
        - α: Absorptionskoeffizient in cm⁻¹
        """
        
        if lambda_um <= 0:
            raise ValueError("Die Wellenlänge muss größer als 0 sein.")
        
        # 1 µm = 10⁻⁴ cm
        lambda_cm = lambda_um * 1e-4
        
        # α = 4πk / λ
        alpha = (4 * math.pi * k) / lambda_cm
        
        return alpha

