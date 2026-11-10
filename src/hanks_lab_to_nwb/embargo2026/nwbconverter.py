"""NWBConverter for Hanks lab fiber photometry dataset."""

from neuroconv import NWBConverter
from neuroconv.datainterfaces import DoricFiberPhotometryInterface

from hanks_lab_to_nwb.interfaces import (
    BpodBehaviorInterface,
    FiberPhotometryArtifactInterface,
    HanksLabProcessedFiberPhotometryInterface,
    SpyglassEpochInterface,
    SpyglassVideoInterface,
)

# The processed fiber photometry signals to convert, one interface each. This is the only list of
# them in the code. Each entry is:
#   (interface name in the converter,
#    key in fp_data["fp_data"]["processed_signals"][region] of fp_data_{session_id}.pkl,
#    key of the series' entry under FiberPhotometry in metadata/fiber_photometry.yaml)
# A new signal also needs that entry in fiber_photometry.yaml, and a line in
# _SERIES_REGION_DESCRIPTION_TEMPLATES in utils/build_metadata.py.
PROCESSED_SIGNALS = [
    ("ProcessedFP_RawIso", "raw_iso", "raw_iso_series"),
    ("ProcessedFP_RawLig", "raw_lig", "raw_lig_series"),
    ("ProcessedFP_FilteredIso", "filtered_iso", "filtered_iso_series"),
    ("ProcessedFP_FilteredLig", "filtered_lig", "filtered_lig_series"),
    ("ProcessedFP_FittedIso", "fitted_iso", "fitted_iso_series"),
    ("ProcessedFP_BaselineIso", "baseline_iso", "baseline_iso_series"),
    ("ProcessedFP_BaselineLig", "baseline_lig", "baseline_lig_series"),
    ("ProcessedFP_BaselineCorrIso", "baseline_corr_iso", "baseline_corr_iso_series"),
    ("ProcessedFP_BaselineCorrLig", "baseline_corr_lig", "baseline_corr_lig_series"),
    ("ProcessedFP_FittedBaselineFbandIso", "fitted_baseline_fband_iso", "fitted_baseline_fband_iso_series"),
    ("ProcessedFP_DFF", "dff_iso", "dff_series"),
    ("ProcessedFP_DFFBaselineFband", "dff_iso_baseline_fband", "dff_baseline_fband_series"),
]


class HanksLabNWBConverter(NWBConverter):
    """Primary conversion class for the Hanks lab fiber photometry dataset.

    The interfaces write to the file in the order listed. FiberPhotometryArtifacts must stay after
    the processed signals, because its rows reference their series.
    """

    data_interface_classes = dict(
        DoricFPIsosbestic=DoricFiberPhotometryInterface,
        DoricFPSignal=DoricFiberPhotometryInterface,
        Video=SpyglassVideoInterface,
        Epoch=SpyglassEpochInterface,
        **{interface_name: HanksLabProcessedFiberPhotometryInterface for interface_name, _, _ in PROCESSED_SIGNALS},
        Behavior=BpodBehaviorInterface,
        FiberPhotometryArtifacts=FiberPhotometryArtifactInterface,
    )
