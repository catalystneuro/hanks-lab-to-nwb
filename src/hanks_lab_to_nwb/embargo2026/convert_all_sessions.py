"""Convert all Hanks lab sessions (WM and bandit task) to NWB."""

import re
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from hanks_lab_to_nwb.embargo2026.convert_session import (
    SESSIONS_FILE_PATH,
    load_session_registry,
    session_to_nwb,
)


def get_session_ids(data_dir_path: Path) -> tuple[list[int], list[int], list[int]]:
    """Compare the sessions in the data folder with the registry in metadata/sessions.yaml.

    A session is in the data folder when it has a ``sess_data_{session_id}.pkl`` file.

    Returns
    -------
    to_convert :
        Sessions that are in the data folder and registered.
    unregistered :
        Sessions that are in the data folder but not registered. They are not converted.
    missing :
        Sessions that are registered but have no ``sess_data_{session_id}.pkl`` in the data folder.
    """
    found = set()
    for pkl_path in data_dir_path.glob("sess_data_*.pkl"):
        match = re.fullmatch(r"sess_data_(\d+)\.pkl", pkl_path.name)
        if match is not None:
            found.add(int(match.group(1)))
    registered = set(load_session_registry()["sessions"])
    return sorted(found & registered), sorted(found - registered), sorted(registered - found)


def _safe_convert(session_id: int, data_dir_path: Path, output_dir_path: Path, stub_test: bool) -> tuple[int, str]:
    """Convert one session, capturing any exception as text.

    Module-level (not a closure) so ProcessPoolExecutor can pickle it — the
    "spawn" start method used on macOS and Windows cannot send a nested function
    to a worker process.
    """
    try:
        nwbfile_path = session_to_nwb(
            session_id=session_id,
            data_dir_path=data_dir_path,
            output_dir_path=output_dir_path,
            stub_test=stub_test,
        )
        return session_id, f"OK {nwbfile_path}"
    except Exception:
        exception_dir = Path(output_dir_path) / "exceptions"
        exception_dir.mkdir(parents=True, exist_ok=True)
        exc_path = exception_dir / f"sess_{session_id}.txt"
        exc_path.write_text(traceback.format_exc())
        return session_id, f"ERROR, see {exc_path}"


def dataset_to_nwb(
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    max_workers: int = 1,
    stub_test: bool = False,
):
    """Convert every registered session found in a data folder.

    Sessions are registered in metadata/sessions.yaml. Sessions in the folder that are not
    registered are listed and not converted. A session that fails does not stop the others: its
    traceback is written to ``<output_dir_path>/exceptions/sess_{session_id}.txt``.

    Parameters
    ----------
    data_dir_path :
        Folder holding the source files of all sessions.
    output_dir_path :
        Folder the .nwb files are written to ("nwb_stub/" inside it when stub_test=True).
    max_workers :
        Number of sessions converted in parallel.
    stub_test :
        If True, write only the first 100 samples of each time series.
    """
    data_dir_path = Path(data_dir_path)
    output_dir_path = Path(output_dir_path)
    exception_dir = output_dir_path / "exceptions"
    exception_dir.mkdir(parents=True, exist_ok=True)

    session_ids, unregistered, missing = get_session_ids(data_dir_path)
    print(f"Converting {len(session_ids)} sessions: {session_ids}", flush=True)
    if unregistered:
        print(
            f"NOT CONVERTED, {len(unregistered)} sessions in {data_dir_path} are not registered: {unregistered}. "
            f"Add them under 'sessions' in {SESSIONS_FILE_PATH} to convert them.",
            flush=True,
        )
    if missing:
        print(
            f"NOT FOUND, {len(missing)} registered sessions have no sess_data_*.pkl in {data_dir_path}: {missing}.",
            flush=True,
        )

    futures = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        for session_id in session_ids:
            futures[executor.submit(_safe_convert, session_id, data_dir_path, output_dir_path, stub_test)] = session_id
        # as_completed surfaces worker results; without it a crashed worker is silent
        for future in as_completed(futures):
            session_id, status = future.result()
            print(f"  sess {session_id}: {status}", flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert all Hanks lab sessions to NWB.")
    parser.add_argument("data_dir_path", type=str)
    parser.add_argument("output_dir_path", type=str)
    parser.add_argument("--max_workers", type=int, default=1)
    parser.add_argument("--stub_test", action="store_true")
    args = parser.parse_args()

    dataset_to_nwb(
        data_dir_path=args.data_dir_path,
        output_dir_path=args.output_dir_path,
        max_workers=args.max_workers,
        stub_test=args.stub_test,
    )
