import numpy as np
from pyueye import ueye
import ctypes  # Import ctypes for checking memory pointer

class CameraService:
    """
    A service class to manage all interactions with the IDS uEye camera.
    This class encapsulates the pyueye library to provide a simple, high-level interface.
    
    MODIFIED: This version avoids continuous streaming to reduce heat.
    It uses single-shot capture mode via is_FreezeVideo.
    """
    def __init__(self):
        """
        Initializes the camera connection and sets up memory for image capture.
        """
        self.h_cam = ueye.HIDS(0)            # 0: first available camera
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.bits_per_pixel = ueye.int(24)    # 24: for 8-bit BGR color mode

        self._initialize_camera()

    def _initialize_camera(self):
        """Handles the low-level camera initialization sequence."""
        ret = ueye.is_InitCamera(self.h_cam, None)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Camera initialization failed.")
            return

        # Get sensor info to determine image size
        sensor_info = ueye.SENSORINFO()
        ueye.is_GetSensorInfo(self.h_cam, sensor_info)
        self.width = sensor_info.nMaxWidth
        self.height = sensor_info.nMaxHeight

        # Set color mode (e.g., 8-bit BGR)
        ret = ueye.is_SetColorMode(self.h_cam, ueye.IS_CM_BGR8_PACKED)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set color mode.")
            self.disconnect()
            return

        # This is crucial for 24-bit color formats to be read correctly.
        ret = ueye.is_SetDisplayMode(self.h_cam, ueye.IS_SET_DM_DIB)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set display mode (DIB).")
            self.disconnect()
            return

        # Allocate memory for one image
        ret = ueye.is_AllocImageMem(self.h_cam, self.width, self.height, self.bits_per_pixel,
                                      self.pc_image_memory, self.mem_id)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Image memory allocation failed.")
            self.disconnect()
            return

        # Set the active image memory
        ret = ueye.is_SetImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set active image memory.")
            self.disconnect()
            return

        self.is_connected = True
        print(f"CameraService: INFO - Camera initialized and ready for single-shot capture (WxH: {self.width.value}x{self.height.value}).")

    def get_status(self):
        """
        Provides the current status of the camera connection.
        """
        return self.is_connected

    def capture_image(self) -> np.ndarray | None:
        """
        Captures a single frame from the camera using single-shot mode.

        Returns:
            np.ndarray: The captured image as a NumPy array, or None if an error occurs.
        """
        if not self.is_connected:
            print("CameraService: ERROR - Cannot capture image, camera is not connected.")
            return None

        # Because is_CaptureVideo was not called, is_FreezeVideo(..., IS_WAIT)
        # will trigger a single frame acquisition, wait for it to complete,
        # and then return. The camera goes back to idle state afterward.
        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            print(f"CameraService: ERROR - Failed to capture single frame. Error code: {ret}")
            return None

        # Copy image data from the camera's memory buffer to a NumPy array
        try:
            bytes_per_pixel = int(self.bits_per_pixel.value / 8)
            
            width_val = self.width.value
            height_val = self.height.value
            
            pitch = width_val * bytes_per_pixel

            image_data = ueye.get_data(self.pc_image_memory, width_val, height_val, self.bits_per_pixel, pitch, True)
            
            # Reshape the 1D array into a 3D image (H, W, Channels)
            image_array = np.reshape(image_data, (height_val, width_val, bytes_per_pixel))

            return image_array.copy() # Return a copy so the buffer can be reused
        
        except Exception as e:
            print(f"CameraService: ERROR - Failed to copy image data: {e}")
            return None

    def disconnect(self):
        """
        Disengages from the camera and releases all allocated resources.
        
        --- MODIFIED ---
        This now properly frees the allocated image memory before exiting.
        """
        if self.is_connected:
            ueye.is_StopLiveVideo(self.h_cam, ueye.IS_WAIT)

            if self.pc_image_memory.value: # Check if the pointer is not null
                ret = ueye.is_FreeImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
                if ret != ueye.IS_SUCCESS:
                    print("CameraService: WARN - Failed to free image memory.")
            
            # Release the camera handle
            ret = ueye.is_ExitCamera(self.h_cam)
            if ret != ueye.IS_SUCCESS:
                print("CameraService: WARN - Failed to exit camera properly.")

            self.is_connected = False
            self.pc_image_memory = ueye.c_mem_p() # Clear the pointer reference
            print("CameraService: INFO - Camera disconnected and resources released.")
        else:
            # Avoid trying to disconnect multiple times
            pass
            
    def __del__(self):
        """
        Destructor to ensure resources are released when the object is garbage collected.
        """
        self.disconnect()