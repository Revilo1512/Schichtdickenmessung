import numpy as np
from pyueye import ueye
import ctypes
from typing import List, Dict, Any

class CameraService:
    """
    A service class to manage all interactions with the IDS uEye camera.
    
    MODIFIED: This version supports camera selection and manual connection.
    It does not connect on init, but waits for a call to connect().
    It still uses single-shot capture mode via is_FreezeVideo.
    """
    def __init__(self):
        """
        Initializes the service without connecting to a camera.
        """
        self.h_cam = ueye.HIDS(0)            # Handle, will be set > 0 on connect
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.model_name = ""
        self.bits_per_pixel = ueye.int(24)    # 24: for 8-bit BGR color mode

    def list_available_cameras(self) -> List[Dict[str, Any]]:
        """
        Gets a list of all available (and not in-use) uEye cameras.
        """
        try:
            # 1. Create an empty UEYE_CAMERA_LIST instance.
            #    The pyueye wrapper pre-allocates space in this structure.
            cam_list = ueye.UEYE_CAMERA_LIST() 

            # 2. Call is_GetCameraList to populate the instance.
            if ueye.is_GetCameraList(cam_list) != ueye.IS_SUCCESS:
                print("CameraService: ERROR - Could not get camera list.")
                return []
            
            # 3. Get the number of cameras from the list's dwCount field.
            n_cameras = int(cam_list.dwCount)
            
            if n_cameras == 0:
                print("CameraService: INFO - No uEye cameras found.")
                return []
                
            result_list = []
            for i in range(n_cameras):
                cam_info = cam_list.uci[i]
                # Only list cameras that are not already in use
                if cam_info.dwInUse == 0:
                    result_list.append({
                        "id": int(cam_info.dwCameraID),
                        # Use .strip() and null-termination check
                        "model": str(cam_info.Model.decode('utf-8').strip('\x00').strip())
                    })
            return result_list
        except Exception as e:
            print(f"CameraService: ERROR - Failed to list cameras: {e}")
            return []

    def connect(self, camera_id: int) -> bool:
        """
        Disconnects any active camera and attempts to initialize the new one.
        """
        if self.is_connected:
            self.disconnect()

        self.h_cam = ueye.HIDS(camera_id)
        
        ret = ueye.is_InitCamera(self.h_cam, None)
        if ret != ueye.IS_SUCCESS:
            print(f"CameraService: ERROR - Camera {camera_id} initialization failed. Code: {ret}")
            self.h_cam = ueye.HIDS(0) # Reset handle
            return False

        # Get sensor info
        sensor_info = ueye.SENSORINFO()
        ueye.is_GetSensorInfo(self.h_cam, sensor_info)
        self.width = sensor_info.nMaxWidth
        self.height = sensor_info.nMaxHeight
        self.model_name = str(sensor_info.strSensorName.decode('utf-8').strip())

        # Set color mode
        ret = ueye.is_SetColorMode(self.h_cam, ueye.IS_CM_BGR8_PACKED)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set color mode.")
            self.disconnect()
            return False

        # Set display mode
        ret = ueye.is_SetDisplayMode(self.h_cam, ueye.IS_SET_DM_DIB)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set display mode (DIB).")
            self.disconnect()
            return False

        # Allocate memory
        ret = ueye.is_AllocImageMem(self.h_cam, self.width, self.height, self.bits_per_pixel,
                                      self.pc_image_memory, self.mem_id)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Image memory allocation failed.")
            self.disconnect()
            return False

        # Set active memory
        ret = ueye.is_SetImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
        if ret != ueye.IS_SUCCESS:
            print("CameraService: ERROR - Failed to set active image memory.")
            self.disconnect()
            return False

        self.is_connected = True
        print(f"CameraService: INFO - Camera {camera_id} ({self.model_name}) initialized (WxH: {self.width.value}x{self.height.value}).")
        return True

    def get_status(self) -> Dict[str, Any]:
        """
        Provides the current status of the camera connection.
        """
        return {
            "connected": self.is_connected,
            "model": self.model_name,
            "width": self.width.value if self.is_connected else 0,
            "height": self.height.value if self.is_connected else 0
        }

    def capture_image(self) -> np.ndarray | None:
        """
        Captures a single frame from the connected camera.
        """
        if not self.is_connected:
            print("CameraService: ERROR - Cannot capture image, camera is not connected.")
            return None

        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            print(f"CameraService: ERROR - Failed to capture single frame. Error code: {ret}")
            return None

        # Copy image data
        try:
            bytes_per_pixel = int(self.bits_per_pixel.value / 8)
            width_val = self.width.value
            height_val = self.height.value
            pitch = width_val * bytes_per_pixel

            image_data = ueye.get_data(self.pc_image_memory, width_val, height_val, self.bits_per_pixel, pitch, True)
            
            image_array = np.reshape(image_data, (height_val, width_val, bytes_per_pixel))

            return image_array.copy()
        
        except Exception as e:
            print(f"CameraService: ERROR - Failed to copy image data: {e}")
            return None

    def disconnect(self):
        """
        Disengages from the camera and releases all allocated resources.
        """
        if self.h_cam.value == 0: # Nothing to do if handle is 0
            return
            
        if self.is_connected:
            ueye.is_StopLiveVideo(self.h_cam, ueye.IS_WAIT)

            if self.pc_image_memory.value:
                ueye.is_FreeImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
            
            ueye.is_ExitCamera(self.h_cam)
        
        print(f"CameraService: INFO - Camera {self.h_cam.value} disconnected.")

        # Reset state
        self.h_cam = ueye.HIDS(0)
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id = ueye.int()
        self.is_connected = False
        self.width = ueye.int()
        self.height = ueye.int()
        self.model_name = ""
            
    def __del__(self):
        """
        Destructor to ensure resources are released.
        """
        self.disconnect()