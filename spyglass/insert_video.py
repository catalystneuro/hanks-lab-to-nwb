"""Insert the behavior video of one or more converted Hanks NWB files into Spyglass.

Spyglass only fills VideoFile for a TaskEpoch, so this fills CameraDevice, IntervalList (the
session's one epoch, from the NWB ``epochs`` table), TaskEpoch (which also fills Task, from the
``processing["tasks"]`` task table) and then VideoFile. The session is registered first if it is
not in the database yet (see ``common.ensure_session``). A session that already has a VideoFile
row is skipped; use ``insert_all_sessions.py`` to reload a re-converted file.

Arguments are file names already in the Spyglass raw dir, or paths to converted NWB files anywhere
on disk (symlinked into the raw dir, not copied):

    conda activate spyglass-photometry
    cd spyglass
    python insert_video.py ../nwb_output/*.nwb
"""

import sys

from common import (
    ensure_session,
    report_insert_errors,
    run_table_groups,
    section,
    stage_in_raw_dir,
)

from spyglass.common.common_behav import VideoFile
from spyglass.common.common_device import CameraDevice
from spyglass.common.common_interval import IntervalList
from spyglass.common.common_task import Task, TaskEpoch

TABLE_GROUPS = [
    [CameraDevice],
    [IntervalList, TaskEpoch],
    [VideoFile],
]


def insert_video(copy_file_name: str) -> None:
    """Fill the camera, epoch, task and video tables for one registered file."""
    key = {"nwb_file_name": copy_file_name}
    if VideoFile & key:
        print(f"{copy_file_name} already has a VideoFile row, skipping")
        return

    section(f"Video: {copy_file_name}")
    run_table_groups(TABLE_GROUPS, copy_file_name)

    for table in (CameraDevice, Task):
        print(f"{table.__name__:<40} {len(table())} row(s)  (shared catalog, whole-table count)")
    for table in (TaskEpoch, VideoFile):
        print(f"{table.__name__:<40} {len(table & key)} row(s)")
    report_insert_errors(copy_file_name)
    print(TaskEpoch & key)
    print(VideoFile & key)

    # Read the video's ImageSeries back through Spyglass; any failure raises.
    image_series = (VideoFile & key).fetch_nwb()[0]["video_file"]
    print(
        f"  {image_series.name!r}: {len(image_series.timestamps)} frames, "
        f"camera {image_series.device.camera_name}, file {image_series.external_file[0]}"
    )


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python insert_video.py NWB_FILE [NWB_FILE ...]")
    for nwb_file in sys.argv[1:]:
        insert_video(ensure_session(stage_in_raw_dir(nwb_file)))


if __name__ == "__main__":
    main()
