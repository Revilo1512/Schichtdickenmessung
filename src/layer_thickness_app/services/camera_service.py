import logging
import numpy as np
from pyueye import ueye
from typing import Any

# Logger initialisieren
logger = logging.getLogger(__name__)

class CameraService:
    """
    A service class to manage all interactions with the IDS uEye camera.
    
    This version supports camera selection and manual connection.
    It does not connect on init, but waits for a call to connect().
    It uses single-shot capture mode via is_FreezeVideo.
    """
    def __init__(self):
        """Initializes the service without connecting to a camera."""
        self.h_cam = ueye.HIDS(0)            # Handle, will be set > 0 on connect
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.model_name = ""
        self.bits_per_pixel = ueye.int(24)    # 24: for 8-bit BGR color mode

    def list_available_cameras(self) -> list[dict[str, Any]]:
        """Gets a list of all available (and not in-use) uEye cameras."""
        try:
            cam_list = ueye.UEYE_CAMERA_LIST() 

            if ueye.is_GetCameraList(cam_list) != ueye.IS_SUCCESS:
                logger.error("Could not get camera list.")
                return []
            
            n_cameras = int(cam_list.dwCount)
            
            if n_cameras == 0:
                logger.info("No uEye cameras found.")
                return []
                
            result_list = []
            for i in range(n_cameras):
                cam_info = cam_list.uci[i]
                # Only list cameras that are not already in use
                if cam_info.dwInUse == 0:
                    result_list.append({
                        "id": int(cam_info.dwCameraID),
                        "model": str(cam_info.Model.decode('utf-8').strip('\x00').strip())
                    })
            return result_list
        except Exception as e:
            logger.exception("Failed to list cameras: %s", e)
            return []

    def connect(self, camera_id: int) -> bool:
        """Disconnects any active camera and attempts to initialize the new one."""
        if self.is_connected:
            self.disconnect()

        self.h_cam = ueye.HIDS(camera_id)
        
        ret = ueye.is_InitCamera(self.h_cam, None)
        if ret != ueye.IS_SUCCESS:
            logger.error("Camera %s initialization failed. Code: %s", camera_id, ret)
            self.h_cam = ueye.HIDS(0)
            return False

        # Get sensor info
        sensor_info = ueye.SENSORINFO()
        ueye.is_GetSensorInfo(self.h_cam, sensor_info)
        self.width = sensor_info.nMaxWidth
        self.height = sensor_info.nMaxHeight
        self.model_name = str(sensor_info.strSensorName.decode('utf-8').strip())

        # Set color mode
        if ueye.is_SetColorMode(self.h_cam, ueye.IS_CM_BGR8_PACKED) != ueye.IS_SUCCESS:
            logger.error("Failed to set color mode.")
            self.disconnect()
            return False

        # Set display mode
        if ueye.is_SetDisplayMode(self.h_cam, ueye.IS_SET_DM_DIB) != ueye.IS_SUCCESS:
            logger.error("Failed to set display mode (DIB).")
            self.disconnect()
            return False

        # Allocate memory
        if ueye.is_AllocImageMem(self.h_cam, self.width, self.height, self.bits_per_pixel,
                                      self.pc_image_memory, self.mem_id) != ueye.IS_SUCCESS:
            logger.error("Image memory allocation failed.")
            self.disconnect()
            return False

        # Set active memory
        if ueye.is_SetImageMem(self.h_cam, self.pc_image_memory, self.mem_id) != ueye.IS_SUCCESS:
            logger.error("Failed to set active image memory.")
            self.disconnect()
            return False

        self.is_connected = True
        logger.info("Camera %s (%s) initialized (WxH: %sx%s).", 
                    camera_id, self.model_name, self.width.value, self.height.value)
        return True

    def get_status(self) -> dict[str, Any]:
        """Provides the current status of the camera connection."""
        return {
            "connected": self.is_connected,
            "model": self.model_name,
            "width": self.width.value if self.is_connected else 0,
            "height": self.height.value if self.is_connected else 0
        }

    def capture_image(self) -> np.ndarray | None:
        """Captures a single frame from the connected camera."""
        if not self.is_connected:
            logger.error("Cannot capture image, camera is not connected.")
            return None

        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            logger.error("Failed to capture single frame. Error code: %s", ret)
            return None

        try:
            bytes_per_pixel = int(self.bits_per_pixel.value / 8)
            width_val = self.width.value
            height_val = self.height.value
            pitch = width_val * bytes_per_pixel

            image_data = ueye.get_data(self.pc_image_memory, width_val, height_val, self.bits_per_pixel, pitch, True)
            image_array = np.reshape(image_data, (height_val, width_val, bytes_per_pixel))

            return image_array.copy()
        
        except Exception as e:
            logger.exception("Failed to copy image data: %s", e)
            return None

    def disconnect(self):
        """Disengages from the camera and releases all allocated resources."""
        if self.h_cam.value == 0:
            return
            
        if self.is_connected:
            ueye.is_StopLiveVideo(self.h_cam, ueye.IS_WAIT)

            if self.pc_image_memory.value:
                ueye.is_FreeImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
            
            ueye.is_ExitCamera(self.h_cam)
        
        logger.info("Camera %s disconnected.", self.h_cam.value)

        # Reset state
        self.h_cam = ueye.HIDS(0)
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.model_name = ""
            
    def __del__(self):
        """Destructor to ensure resources are released."""
        self.disconnect()