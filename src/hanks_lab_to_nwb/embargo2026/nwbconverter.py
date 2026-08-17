"""NWBConverter for Hanks lab fiber photometry dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import DoricFiberPhotometryInterface

from hanks_lab_to_nwb.interfaces import HanksLabProcessedFiberPhotometryInterface


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset."""

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
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
        pass
