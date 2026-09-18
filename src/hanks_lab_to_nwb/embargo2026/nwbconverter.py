"""NWBConverter for Hanks lab fiber photometry dataset."""

import h5py
import numpy as np
from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    DoricFiberPhotometryInterface,
    ExternalVideoInterface,
)


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset."""

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
        Video=ExternalVideoInterface,
    )

    def temporally_align_data_interfaces(self, metadata=None, conversion_options=None):
        if "Video" not in self.data_interface_objects:
            return
        mp4_path = self.data_interface_objects["Video"].source_data["file_paths"][0]
        doric_path = mp4_path.with_suffix(".doric")
        with h5py.File(doric_path, "r") as f:
            timestamps = np.asarray(f["DataAcquisition/BehaviorCamera/Video/Series0001/DMK-33UX290/Time"][:])
        self.data_interface_objects["Video"].set_aligned_timestamps([timestamps])
