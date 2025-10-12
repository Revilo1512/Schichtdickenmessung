import numpy as np
from pyueye import ueye

class CameraService:
    """
    A service class to manage all interactions with the IDS uEye camera.
    This class encapsulates the pyueye library to provide a simple, high-level interface.
    """
    def __init__(self):
        """
        Initializes the camera connection and sets up memory for image capture.
        """
        self.h_cam = ueye.HIDS(0)             # 0: first available camera
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.bits_per_pixel = ueye.int(24)    # 24: for 8-bit color modes

        self._initialize_camera()

    def _initialize_camera(self):
        """Handles the low-level camera initialization sequence."""
        ret = ueye.is_InitCamera(self.h_cam, None)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Camera initialization failed.")
            return

        # Get sensor info to determine image size
        sensor_info = ueye.IS_SENSORINFO()
        ueye.is_GetSensorInfo(self.h_cam, sensor_info)
        self.width = sensor_info.nMaxWidth
        self.height = sensor_info.nMaxHeight

        # Set color mode (e.g., 8-bit monochrome)
        ret = ueye.is_SetColorMode(self.h_cam, ueye.IS_CM_MONO8)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set color mode.")
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
            
        # Start continuous video capture (freerun mode)
        ret = ueye.is_CaptureVideo(self.h_cam, ueye.IS_DONT_WAIT)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to start video capture.")
            self.disconnect()
            return

        self.is_connected = True
        print(f"CameraService: INFO - Camera successfully initialized (WxH: {self.width.value}x{self.height.value}).")

    def get_status(self):
        """
        Provides the current status of the camera connection.
        """
        return self.is_connected

    def capture_image(self) -> np.ndarray | None:
        """
        Captures a single frame from the camera.

        Returns:
            np.ndarray: The captured image as a NumPy array, or None if an error occurs.
        """
        if not self.is_connected:
            print("CameraService: ERROR - Cannot capture image, camera is not connected.")
            return None

        # Freeze the video to capture a single frame
        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to freeze video frame.")
            return None

        # Copy image data from the camera's memory buffer to a NumPy array
        try:
            image_data = ueye.get_data(self.pc_image_memory, self.width, self.height, self.bits_per_pixel, 0)
            
            # Reshape the 1D array into a 2D image (for monochrome)
            # The bits per pixel might differ for color, so adjust accordingly.
            bytes_per_pixel = int(self.bits_per_pixel.value / 8)
            image_array = np.reshape(image_data, (self.height.value, self.width.value, bytes_per_pixel))
            
            # For MONO8, we can remove the last dimension
            if bytes_per_pixel == 1:
                image_array = np.squeeze(image_array, axis=-1)

            return image_array
        except Exception as e:
            print(f"CameraService: ERROR - Failed to copy image data: {e}")
            return None

    def disconnect(self):
        """
        Disconnects from the camera and releases all resources.
        """
        if self.is_connected:
            ueye.is_ExitCamera(self.h_cam)
            self.is_connected = False
            print("CameraService: INFO - Camera disconnected.")
