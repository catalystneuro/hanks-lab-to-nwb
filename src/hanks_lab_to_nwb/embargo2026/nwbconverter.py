"""NWBConverter for Hanks lab fiber photometry dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import DoricFiberPhotometryInterface

from hanks_lab_to_nwb.interfaces import BpodBehaviorInterface


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset."""

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
        Behavior=BpodBehaviorInterface,
    )

    def temporally_align_data_interfaces(self, metadata=None, conversion_options=None):
        pass
