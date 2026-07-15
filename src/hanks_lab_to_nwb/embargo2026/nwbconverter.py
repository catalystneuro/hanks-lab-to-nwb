"""NWBConverter for Hanks lab fiber photometry dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import DoricFiberPhotometryInterface


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset."""

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
    )

    def temporally_align_data_interfaces(self, metadata=None, conversion_options=None):
        pass
