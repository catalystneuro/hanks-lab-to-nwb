"""Convert all Hanks lab sessions (WM and bandit task) to NWB."""

import pickle
import re
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from hanks_lab_to_nwb.embargo2026.convert_session import (
    _SESSION_AIN_TO_REGION,
    session_to_nwb,
)

_KNOWN_PROTOCOLS = {"ClassicRLTasks", "ToneCatDelayResp"}


def get_session_ids(data_dir_path: Path) -> list[int]:
    """Return session IDs that have a known AIN→region mapping and a recognised protocol."""
    session_ids = []
    for pkl_path in sorted(data_dir_path.glob("sess_data_*.pkl")):
        m = re.match(r"sess_data_(\d+)\.pkl", pkl_path.name)
        if m is None:
            continue
        session_id = int(m.group(1))
        if session_id not in _SESSION_AIN_TO_REGION:
            continue
        with open(pkl_path, "rb") as f:
            df = pickle.load(f)
        if df["protocol"].iloc[0] not in _KNOWN_PROTOCOLS:
            continue
        session_ids.append(session_id)
    return session_ids


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
        return session_id, f"ERROR — see {exc_path}"


def dataset_to_nwb(
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    max_workers: int = 1,
    stub_test: bool = False,
):
    data_dir_path = Path(data_dir_path)
    output_dir_path = Path(output_dir_path)
    exception_dir = output_dir_path / "exceptions"
    exception_dir.mkdir(parents=True, exist_ok=True)

    session_ids = get_session_ids(data_dir_path)
    print(f"Found {len(session_ids)} sessions: {session_ids}", flush=True)

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
