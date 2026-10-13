"""Behavior video interface whose camera is a Spyglass-compatible ndx-franklab-novela CameraDevice."""

from copy import deepcopy

import h5py
import numpy as np
from ndx_franklab_novela import CameraDevice
from neuroconv.datainterfaces import ExternalVideoInterface
from pydantic import FilePath
from pynwb import NWBFile
from pynwb.device import DeviceModel

DORIC_CAMERA_TIME_PATH = "DataAcquisition/BehaviorCamera/Video/Series0001/DMK-33UX290/Time"


class SpyglassVideoInterface(ExternalVideoInterface):
    """ExternalVideoInterface for the Doric behavior camera, written with a Spyglass CameraDevice.

    Spyglass's ``VideoFile`` table reads the camera from the ImageSeries' device and only accepts an
    ``ndx_franklab_novela.CameraDevice``. ``add_to_nwbfile`` adds that device under the name of the
    video's ``Devices`` entry before calling ``ExternalVideoInterface.add_to_nwbfile``, which reuses
    a device of the same name, so the ImageSeries links to it.

    Frame timestamps come from the ``mov_{session_id}.doric`` sidecar, which is on the Doric clock.
    """

    def __init__(
        self,
        file_path: FilePath,
        timestamps_file_path: FilePath,
        verbose: bool = False,
        *,
        metadata_key: str = "behavior_video",
        video_name: str = "BehaviorVideo",
    ):
        """
        Parameters
        ----------
        file_path : FilePath
            The ``mov_{session_id}.mp4`` video.
        timestamps_file_path : FilePath
            The ``mov_{session_id}.doric`` sidecar holding one timestamp per frame.
        metadata_key : str
            Key of this video's entry in ``metadata["Behavior"]["ExternalVideos"]``.
        video_name : str
            Name of the ImageSeries.
        """
        super().__init__(file_paths=[file_path], verbose=verbose, metadata_key=metadata_key, video_name=video_name)
        self.source_data["timestamps_file_path"] = str(timestamps_file_path)
        self.set_aligned_timestamps(self.get_original_timestamps())

    def get_original_timestamps(self, stub_test: bool = False) -> list[np.ndarray]:
        with h5py.File(self.source_data["timestamps_file_path"], "r") as f:
            return [np.asarray(f[DORIC_CAMERA_TIME_PATH][:])]

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Behavior"]["properties"]["Video"] = {
            "type": "object",
            "properties": {
                "CameraDevice": {
                    "description": "Spyglass fields of each camera, which is written as an ndx-franklab-novela CameraDevice.",
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "device_metadata_key": {
                                "type": "string",
                                "description": (
                                    "Key of the camera's entry in metadata['Devices'], which gives its name, "
                                    "description, serial number and model. Spyglass takes the camera ID from the "
                                    "first whitespace-separated integer in the name, e.g. 'behavior_camera 0'."
                                ),
                            },
                            "camera_name": {"type": "string", "description": "Name Spyglass shows for the camera."},
                            "frame_rate": {"type": "number", "description": "Frame rate in Hz."},
                            "lens": {"type": "string", "description": "Lens of the camera."},
                            "meters_per_pixel": {"type": "number", "description": "Size of one pixel in meters."},
                        },
                        "required": ["device_metadata_key", "camera_name", "frame_rate", "lens", "meters_per_pixel"],
                    },
                },
            },
            "required": ["CameraDevice"],
        }
        return metadata_schema

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict | None = None, **conversion_options):
        metadata = deepcopy(metadata)
        device_metadata_key = metadata["Behavior"]["ExternalVideos"][self.metadata_key]["device_metadata_key"]
        camera_metadata = next(
            camera
            for camera in metadata["Behavior"]["Video"]["CameraDevice"]
            if camera["device_metadata_key"] == device_metadata_key
        )
        device_metadata = metadata["Devices"][device_metadata_key]
        if device_metadata["name"] not in nwbfile.devices:
            model_metadata = metadata["DeviceModels"][device_metadata["device_model_metadata_key"]]
            model = nwbfile.device_models.get(model_metadata["name"])
            if model is None:
                model = DeviceModel(**model_metadata)
                nwbfile.add_device_model(model)
            nwbfile.add_device(
                CameraDevice(
                    name=device_metadata["name"],
                    description=device_metadata["description"],
                    serial_number=device_metadata["serial_number"],
                    model=model,
                    camera_name=camera_metadata["camera_name"],
                    frame_rate=camera_metadata["frame_rate"],
                    lens=camera_metadata["lens"],
                    meters_per_pixel=camera_metadata["meters_per_pixel"],
                )
            )
        super().add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **conversion_options)
