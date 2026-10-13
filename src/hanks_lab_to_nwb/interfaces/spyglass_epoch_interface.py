"""Session epoch and task table, in the layout Spyglass reads into IntervalList, Task and TaskEpoch."""

import h5py
import numpy as np
from neuroconv.basedatainterface import BaseDataInterface
from pydantic import FilePath
from pynwb import NWBFile
from pynwb.core import DynamicTable

from hanks_lab_to_nwb.interfaces.spyglass_video_interface import DORIC_CAMERA_TIME_PATH


class SpyglassEpochInterface(BaseDataInterface):
    """One epoch spanning the behavior video, and a ``processing["tasks"]["task_table"]``.

    Each session is one continuous recording, so it has one epoch, tagged "01" (Spyglass's epoch
    name), from the first to the last frame time in the ``mov_{session_id}.doric`` sidecar (Doric
    clock). The task table has one row per ``metadata["Tasks"]`` entry, each performed in that epoch.
    """

    keywords = ("behavior", "task")

    def __init__(self, file_path: FilePath, verbose: bool = False):
        """
        Parameters
        ----------
        file_path : FilePath
            The ``mov_{session_id}.doric`` behavior camera sidecar.
        """
        super().__init__(file_path=str(file_path), verbose=verbose)

    def get_epoch_start_and_stop_time(self) -> tuple[float, float]:
        with h5py.File(self.source_data["file_path"], "r") as f:
            frame_times = f[DORIC_CAMERA_TIME_PATH]
            return float(frame_times[0]), float(frame_times[-1])

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Tasks"] = {
            "description": "Tasks performed in the session's epoch, one task_table row each.",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the task (the Bpod protocol)."},
                    "description": {"type": "string", "description": "Description of the task."},
                    "camera_id": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "IDs of the cameras recording the task (the integer in each camera's name).",
                    },
                },
                "required": ["name", "description", "camera_id"],
            },
        }
        return metadata_schema

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict):
        start_time, stop_time = self.get_epoch_start_and_stop_time()
        nwbfile.add_epoch(start_time=start_time, stop_time=stop_time, tags=["01"])

        task_table = DynamicTable(name="task_table", description="Task performed in each epoch.")
        task_table.add_column(name="task_name", description="Name of the task (Bpod protocol).")
        task_table.add_column(name="task_description", description="Description of the task.")
        task_table.add_column(name="camera_id", description="IDs of the cameras recording the task.")
        task_table.add_column(name="task_epochs", description="Epochs in which the task was performed.")
        for task_metadata in metadata["Tasks"]:
            task_table.add_row(
                task_name=task_metadata["name"],
                task_description=task_metadata["description"],
                camera_id=np.asarray(task_metadata["camera_id"], dtype=np.int32),
                task_epochs=[1],
            )
        tasks_module = nwbfile.create_processing_module(name="tasks", description="Tasks performed in the session.")
        tasks_module.add(task_table)
