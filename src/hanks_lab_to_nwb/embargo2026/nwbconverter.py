"""NWBConverter for Hanks lab fiber photometry dataset."""

import h5py
import numpy as np
from neuroconv import NWBConverter
from neuroconv.datainterfaces import (
    DoricFiberPhotometryInterface,
    ExternalVideoInterface,
)

from hanks_lab_to_nwb.interfaces import HanksLabProcessedFiberPhotometryInterface


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset."""

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
        Video=ExternalVideoInterface,
        # Processed signals — one entry per signal type (all share the same class).
        ProcessedFP_RawIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_RawLig=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_FilteredIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_FilteredLig=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_FittedIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_BaselineIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_BaselineLig=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_BaselineCorrIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_BaselineCorrLig=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_FittedBaselineFbandIso=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_DFF=HanksLabProcessedFiberPhotometryInterface,
        ProcessedFP_DFFBaselineFband=HanksLabProcessedFiberPhotometryInterface,
    )

    def temporally_align_data_interfaces(self, metadata=None, conversion_options=None):
        if "Video" not in self.data_interface_objects:
            return
        mp4_path = self.data_interface_objects["Video"].source_data["file_paths"][0]
        doric_path = mp4_path.with_suffix(".doric")
        with h5py.File(doric_path, "r") as f:
            timestamps = np.asarray(f["DataAcquisition/BehaviorCamera/Video/Series0001/DMK-33UX290/Time"][:])
        self.data_interface_objects["Video"].set_aligned_timestamps([timestamps])
