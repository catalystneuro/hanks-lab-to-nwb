"""Load every converted Hanks NWB file in a folder into Spyglass: the session, its fiber photometry, its
artifact intervals and its video.

Each file's existing entry is deleted first, so this is the script to run after re-converting.
To add one modality to sessions that are already loaded, run ``insert_fiber_photometry.py``,
``insert_intervals.py`` or ``insert_video.py`` instead.

    conda activate spyglass-photometry
    cd spyglass
    python insert_all_sessions.py ../nwb_output
"""

import sys
from pathlib import Path

from common import reload_session, section, stage_in_raw_dir
from insert_fiber_photometry import insert_fiber_photometry
from insert_intervals import insert_intervals
from insert_video import insert_video


def insert_all_sessions(nwb_folder_path: str) -> None:
    """Reload and insert every ``.nwb`` file directly inside ``nwb_folder_path``."""
    nwb_files = sorted(Path(nwb_folder_path).expanduser().glob("*.nwb"))
    if not nwb_files:
        raise FileNotFoundError(f"No .nwb files in {nwb_folder_path}")
    for nwb_file in nwb_files:
        copy_file_name = reload_session(stage_in_raw_dir(str(nwb_file)))
        insert_fiber_photometry(copy_file_name)
        insert_intervals(copy_file_name)
        insert_video(copy_file_name)
        section(f"DONE: {nwb_file.name}")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python insert_all_sessions.py NWB_FOLDER_PATH")
    insert_all_sessions(sys.argv[1])


if __name__ == "__main__":
    main()
