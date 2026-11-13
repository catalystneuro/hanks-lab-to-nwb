"""Insert the Bpod behavior of one or more converted Hanks NWB files into Spyglass.

The behavior is stored with ``ndx-structured-behavior``: the task's action, event and state types in
``lab_meta_data["task"]``, and every recorded action, event and state in
``acquisition["task_recording"]``. LorenFrankLab/spyglass#1349 ingests them into
``common_task_rec``:

- ``TaskRecordingTypes`` (one row per file) and its parts ``ActionTypes``, ``EventTypes``,
  ``StateTypes`` and ``Arguments``, one row per type or task argument.
- ``TaskRecording``: the object IDs of the actions, events and states tables and of the file's
  ``trials`` table. The rows stay in the NWB file and are read with ``fetch1_dataframe()``.

The session is registered first if it is not in the database yet (see ``common.ensure_session``).
A session that already has a ``TaskRecording`` row is skipped; use ``insert_all_sessions.py`` to
reload a re-converted file.

Arguments are file names already in the Spyglass raw dir, or paths to converted NWB files anywhere
on disk (symlinked into the raw dir, not copied):

    conda activate spyglass-photometry
    cd spyglass
    python insert_behavior.py ../nwb_output/*.nwb
"""

import sys

from common import (
    ensure_session,
    report_insert_errors,
    run_table_groups,
    section,
    stage_in_raw_dir,
)

from spyglass.common.common_nwbfile import Nwbfile
from spyglass.common.common_task_rec import TaskRecording, TaskRecordingTypes
from spyglass.utils.nwb_helper_fn import get_nwb_file

TYPE_PARTS = [
    TaskRecordingTypes.ActionTypes,
    TaskRecordingTypes.EventTypes,
    TaskRecordingTypes.StateTypes,
    TaskRecordingTypes.Arguments,
]
# Same order as populate_all_common(): the master, its parts, then TaskRecording.
TABLE_GROUPS = [
    [TaskRecordingTypes, *TYPE_PARTS, TaskRecording],
]


def insert_behavior(copy_file_name: str) -> None:
    """Fill the structured-behavior tables for one registered file and read every table back."""
    key = {"nwb_file_name": copy_file_name}
    if TaskRecording & key:
        print(f"{copy_file_name} already has a TaskRecording row, skipping")
        return

    section(f"Bpod behavior: {copy_file_name}")
    run_table_groups(TABLE_GROUPS, copy_file_name)

    for table in (TaskRecordingTypes, *TYPE_PARTS, TaskRecording):
        print(f"{table.__name__:<40} {len(table & key)} row(s)")
    report_insert_errors(copy_file_name)
    if not TaskRecording & key:
        raise RuntimeError(f"No TaskRecording row for {copy_file_name}")

    # Read every recorded table back through Spyglass and compare with the file; any mismatch raises.
    nwbfile = get_nwb_file(Nwbfile.get_abs_path(copy_file_name))
    recording = nwbfile.acquisition["task_recording"]
    expected = {
        "actions": len(recording.actions),
        "events": len(recording.events),
        "states": len(recording.states),
        "trials": len(nwbfile.trials),
    }
    for table_name, n_rows in expected.items():
        df = (TaskRecording & key).fetch1_dataframe(table_name)
        if len(df) != n_rows:
            raise RuntimeError(f"{copy_file_name}: {table_name} has {len(df)} rows, the file has {n_rows}")
        print(f"  {table_name}: {len(df)} rows")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python insert_behavior.py NWB_FILE [NWB_FILE ...]")
    for nwb_file in sys.argv[1:]:
        insert_behavior(ensure_session(stage_in_raw_dir(nwb_file)))


if __name__ == "__main__":
    main()
