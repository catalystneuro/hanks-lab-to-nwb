"""Insert the fiber photometry of one or more converted Hanks NWB files into Spyglass.

Fills the photometry device catalog (Indicator, ExcitationSource, Photodetector, DichroicMirror,
OpticalFilter, OpticalFiber), FiberPhotometryConfig and FiberPhotometryResponseSeries. The session
is registered first if it is not in the database yet (see ``common.ensure_session``). A session
that already has photometry rows is skipped; use ``insert_all_sessions.py`` to reload a re-converted file.

Arguments are file names already in the Spyglass raw dir, or paths to converted NWB files anywhere
on disk (symlinked into the raw dir, not copied):

    conda activate spyglass-photometry
    cd spyglass
    python insert_fiber_photometry.py ../nwb_output/*.nwb
"""

import sys

from common import (
    ensure_session,
    report_insert_errors,
    run_table_groups,
    section,
    stage_in_raw_dir,
)

from spyglass.common.common_photometry import (
    DichroicMirror,
    ExcitationSource,
    FiberPhotometryConfig,
    FiberPhotometryResponseSeries,
    Indicator,
    OpticalFiber,
    OpticalFilter,
    Photodetector,
)
from spyglass.common.common_region import BrainRegion

DEVICE_CATALOG = [Indicator, ExcitationSource, Photodetector, DichroicMirror, OpticalFilter, OpticalFiber]
TABLE_GROUPS = [
    DEVICE_CATALOG,
    [FiberPhotometryConfig, FiberPhotometryResponseSeries],
]


def insert_fiber_photometry(copy_file_name: str) -> None:
    """Fill the photometry tables for one registered file and read every series back."""
    key = {"nwb_file_name": copy_file_name}
    if FiberPhotometryConfig & key:
        print(f"{copy_file_name} already has fiber photometry rows, skipping")
        return

    section(f"Fiber photometry: {copy_file_name}")
    run_table_groups(TABLE_GROUPS, copy_file_name)

    config = FiberPhotometryConfig & key
    series = FiberPhotometryResponseSeries & key
    for table in DEVICE_CATALOG + [BrainRegion]:
        print(f"{table.__name__:<40} {len(table())} row(s)  (shared catalog, whole-table count)")
    print(f"{'FiberPhotometryConfig':<40} {len(config)} row(s)")
    print(f"{'FiberPhotometryResponseSeries':<40} {len(series)} row(s)")
    print(f"{'FiberPhotometryResponseSeries.Fiber':<40} {len(FiberPhotometryResponseSeries.Fiber & key)} row(s)")
    report_insert_errors(copy_file_name)
    print(
        (config * BrainRegion).proj(
            "region_name",
            "optical_fiber_name",
            "photodetector_name",
            "excitation_filter_name",
            "excitation_wavelength_in_nm",
            "hemisphere",
            "ap_location",
            "ml_location",
            "dv_location",
        )
    )

    # Read every series back through Spyglass's accessor; any failure raises.
    for series_key in series.fetch("KEY"):
        df = (FiberPhotometryResponseSeries & series_key).fetch1_dataframe()
        name = (FiberPhotometryResponseSeries & series_key).fetch1("name")
        print(f"  {name!r}: shape={df.shape}, t={df.index[0]:.4f}-{df.index[-1]:.4f}")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python insert_fiber_photometry.py NWB_FILE [NWB_FILE ...]")
    for nwb_file in sys.argv[1:]:
        insert_fiber_photometry(ensure_session(stage_in_raw_dir(nwb_file)))


if __name__ == "__main__":
    main()
