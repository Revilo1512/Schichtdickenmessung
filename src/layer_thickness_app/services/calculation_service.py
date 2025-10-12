import math
import cv2
import numpy as np

class CalculationService:
    """
    Used to calculate the thickness of layer after a measurement has been done.
    """
    def __init__(self):
        pass

    def calculate_mean_pixel_value(image, bildcounter):
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_pixel_value = np.mean(gray_image)
        print(f"Mittlerer Grauwert des {bildcounter} Bildes: {mean_pixel_value}")
        return mean_pixel_value

    def linearize_mean_pixel_value(GW):
        GWnorm_lin = (((GW / 255) + 0.055) / 1.005) ** 2.4
        print(f"Linearisierter Grauwert: {GWnorm_lin}")
        return GWnorm_lin

    def berechne_x(I, I1, f):
        if I == 0 or I1 == 0 or f == 0:
            print("Ungültige Eingabewerte. Stellen Sie sicher, dass I, I1 und f nicht null sind.")
            return None
        x = math.log(I1 / I) * (1 / -f)
        print("Die Dicke der Probe ist:", x, "cm")
        ergebnis_in_10hochminus7 = x * 1e7
        return ergebnis_in_10hochminus7

    def berechne_alpha(k: float, lambda_um: float) -> float:
        """
        Berechnet den Absorptionskoeffizienten α [cm⁻¹] aus:
        - k: Extinktionskoeffizient (dimensionslos)
        - lambda_um: Wellenlänge in Mikrometer [µm]

        Rückgabe:
        - α: Absorptionskoeffizient in cm⁻¹
        """
        # Eingabevalidierung: Die Wellenlänge darf nicht kleiner oder gleich 0 sein.
        if lambda_um <= 0:
            raise ValueError("Die Wellenlänge muss größer als 0 sein.")
        
        # Umrechnung der Wellenlänge von Mikrometer (µm) in Zentimeter (cm)
        # 1 µm = 10⁻⁴ cm
        lambda_cm = lambda_um * 1e-4
        
        # Berechnung des Absorptionskoeffizienten nach der Formel α = 4πk / λ
        alpha = (4 * math.pi * k) / lambda_cm
        
        return alpha

"""
# --------------------- Initialisieren der Variablen ---------------------
bildcounter = 0
grey_values = []
grey_values_lin = []
f_wert = 679970			

# Verwendete Wellenlänge sind 635 nm
# f_wert ist der Absorptionskoeffizient ALPHA in cm⁻¹ von https://refractiveindex.info/
# Hier verwendet Kupfer von "Johnson and Christy 1972: n,k 0.188-1.937 µm", bei 635 nm Wellenlänge

# --------------------- while-Schleife ---------------------
while (bildcounter != 2):
    input("Drücke Enter zum Auslösen")
    array = ueye.get_data(pcImageMemory, width, height, nBitsPerPixel, pitch, copy=False)
    frame = np.reshape(array, (height.value, width.value, bytes_per_pixel))
    cv2.imshow("SimpleLive_Python_uEye_OpenCV", frame)

    mean_pixel_value = calculate_mean_pixel_value(frame, bildcounter)
    grey_values.append(mean_pixel_value)

    lin_pixel_value = linearize_mean_pixel_value(mean_pixel_value)
    grey_values_lin.append(lin_pixel_value)

    bildcounter += 1

# --------------------- Berechnung des Ergebnisses ---------------------
if len(grey_values) >= 2:
    ergebnis_x = berechne_x(grey_values_lin[0], grey_values_lin[1], f_wert)
    print("Die Dicke der Probe ist:", ergebnis_x, "nm")
else:
    print("Nicht genügend Daten in der Liste für die Berechnung.")
"""