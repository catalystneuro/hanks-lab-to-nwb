"""Insert the fiber photometry artifact windows of one or more converted Hanks NWB files into Spyglass.

The windows are in the NWB table ``intervals["fiber_photometry_artifacts_intervals"]``, one row per
window with the ``location`` (brain region) it masks. Spyglass's own ingestion only reads the
``epochs`` (and, with LorenFrankLab/spyglass#1349, ``invalid_times``) tables, so this script reads
the table itself and inserts one ``IntervalList`` row per region and artifact type, named
``"fiber photometry artifacts <region> <artifact_type>"``, holding those windows in time order.
``IntervalList`` has no column for the type, so it is part of the name; all of a region's windows
are the rows matching ``"fiber photometry artifacts <region> %"``.

The session is registered first if it is not in the database yet (see ``common.ensure_session``).
A session that already has artifact rows is skipped; use ``insert_all_sessions.py`` to reload a
re-converted file.

Arguments are file names already in the Spyglass raw dir, or paths to converted NWB files anywhere
on disk (symlinked into the raw dir, not copied):

    conda activate spyglass-photometry
    cd spyglass
    python insert_intervals.py ../nwb_output/*.nwb
"""

import sys

import numpy as np
from common import ensure_session, section, stage_in_raw_dir

from spyglass.common.common_interval import IntervalList
from spyglass.common.common_nwbfile import Nwbfile
from spyglass.utils.nwb_helper_fn import get_nwb_file

ARTIFACTS_TABLE_NAME = "fiber_photometry_artifacts_intervals"
INTERVAL_LIST_PREFIX = "fiber photometry artifacts "
PIPELINE = "fiber_photometry"  # what common_photometry sets on its series' valid times


def artifact_interval_lists(copy_file_name: str) -> dict[str, np.ndarray]:
    """Return ``{interval_list_name: (n, 2) array of [start, stop]}``, one entry per region and type."""
    nwbfile = get_nwb_file(Nwbfile.get_abs_path(copy_file_name))
    table = nwbfile.intervals.get(ARTIFACTS_TABLE_NAME) if nwbfile.intervals else None
    if table is None:
        return {}
    df = table.to_dataframe()[["start_time", "stop_time", "location", "artifact_type"]]
    return {
        f"{INTERVAL_LIST_PREFIX}{location} {artifact_type}": rows.sort_values("start_time")[
            ["start_time", "stop_time"]
        ].to_numpy()
        for (location, artifact_type), rows in df.groupby(["location", "artifact_type"])
    }


def insert_intervals(copy_file_name: str) -> None:
    """Insert one IntervalList row per region and artifact type, for one registered file."""
    key = {"nwb_file_name": copy_file_name}
    existing = IntervalList & key & f'interval_list_name LIKE "{INTERVAL_LIST_PREFIX}%"'
    if existing:
        print(f"{copy_file_name} already has artifact IntervalList rows, skipping")
        return

    section(f"Fiber photometry artifact intervals: {copy_file_name}")
    interval_lists = artifact_interval_lists(copy_file_name)
    if not interval_lists:
        print(f"No {ARTIFACTS_TABLE_NAME} table in {copy_file_name}")
        return

    IntervalList.insert(
        [
            dict(key, interval_list_name=name, valid_times=valid_times, pipeline=PIPELINE)
            for name, valid_times in interval_lists.items()
        ]
    )

    # Read every list back and compare with the NWB table; any mismatch raises.
    for name, valid_times in interval_lists.items():
        stored = (IntervalList & key & {"interval_list_name": name}).fetch1("valid_times")
        np.testing.assert_array_equal(stored, valid_times)
        print(f"  {name!r}: {len(stored)} window(s)")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python insert_intervals.py NWB_FILE [NWB_FILE ...]")
    for nwb_file in sys.argv[1:]:
        insert_intervals(ensure_session(stage_in_raw_dir(nwb_file)))


if __name__ == "__main__":
    main()
