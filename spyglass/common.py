"""Shared setup for the Hanks Spyglass loaders: database connection, file staging and the session.

Importing this module loads ``dj_local_conf.json`` and connects BEFORE any spyglass import, so the
loaders import it first. Spyglass declares its schemas at import time and would otherwise connect
with the global ``~/.datajoint_config.json``.

The loaders follow Spyglass's own mechanics:
  - the copy+register step is the same two lines ``insert_sessions()`` runs before calling
    ``populate_all_common()``;
  - the per-table inserts go through Spyglass's ``single_transaction_make()`` helper, with trimmed
    ``tables`` lists grouped and ordered the same way ``populate_all_common()`` does.
"""

from pathlib import Path

import datajoint as dj

CONF = Path(__file__).with_name("dj_local_conf.json")

dj.config.load(str(CONF))
dj.conn(use_tls=False)

from spyglass.common.common_interval import IntervalList  # noqa: E402
from spyglass.common.common_lab import (  # noqa: E402
    Institution,
    Lab,
    LabMember,
    LabTeam,
)
from spyglass.common.common_nwbfile import Nwbfile  # noqa: E402
from spyglass.common.common_session import Session  # noqa: E402
from spyglass.common.common_subject import Subject  # noqa: E402
from spyglass.common.common_usage import InsertError  # noqa: E402
from spyglass.common.populate_all_common import single_transaction_make  # noqa: E402
from spyglass.data_import.insert_sessions import copy_nwb_link_raw_ephys  # noqa: E402
from spyglass.settings import raw_dir  # noqa: E402
from spyglass.utils.nwb_helper_fn import get_nwb_copy_filename  # noqa: E402

SESSION_TABLE_GROUPS = [
    [Institution, Lab, LabMember, LabTeam, Subject],  # parents Session's FKs require
    [Session, Session.Experimenter],
    # The NWB epochs and invalid_times tables: epoch "01" (which TaskEpoch needs) and the fiber
    # photometry artifact windows, "invalid_<region>_<artifact_type>".
    [IntervalList],
]


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def stage_in_raw_dir(nwb_file: str) -> str:
    """Return the file name in the Spyglass raw dir, symlinking an outside path into it."""
    source = Path(nwb_file).expanduser()
    if source.parent == Path("."):  # bare file name: expected to already be in raw_dir
        return source.name
    target = Path(raw_dir) / source.name
    if not target.exists():
        target.symlink_to(source.resolve())
        print(f"Linked {source.resolve()} -> {target}")
    return source.name


def run_table_groups(table_groups: list, copy_file_name: str) -> None:
    """Fill each group of tables for one file in its own transaction, raising on any failure."""
    error_constants = dict(
        dj_user=dj.config["database.user"],
        connection_id=dj.conn().connection_id,
        nwb_file_name=copy_file_name,
    )
    for tables in table_groups:
        single_transaction_make(
            tables=tables,
            nwb_file_name=copy_file_name,
            raise_err=True,
            error_constants=error_constants,
            # single_transaction_make()'s body does config.get(...) unconditionally --
            # the `config: dict = None` default is not None-safe.
            config={},
        )


def ensure_session(nwb_file_name: str) -> str:
    """Register the file, its Session and its IntervalList unless already there; return the copy's file name.

    The copy in the raw dir (stem + "_.nwb") is what Spyglass keys every table on. An already
    registered file is left alone, so a modality can be added without touching the others. After
    re-converting a file, use ``reload_session()`` (``insert_all_sessions.py``) so the copy is refreshed.
    """
    nwbfile_path = Path(raw_dir) / nwb_file_name
    if not nwbfile_path.exists():
        raise FileNotFoundError(f"Expected NWB file at {nwbfile_path}")
    copy_file_name = get_nwb_copy_filename(nwb_file_name)
    if Nwbfile & {"nwb_file_name": copy_file_name}:
        print(f"{copy_file_name} is already registered")
        return copy_file_name

    section(f"Copy, register and insert the session: {nwb_file_name}")
    copy_nwb_link_raw_ephys(nwb_file_name, copy_file_name)
    Nwbfile().insert_from_relative_file_name(copy_file_name)
    run_table_groups(SESSION_TABLE_GROUPS, copy_file_name)
    key = {"nwb_file_name": copy_file_name}
    print(f"Session rows: {len(Session & key)}")
    names = (IntervalList & key).fetch("interval_list_name")
    print(f"IntervalList rows: {len(names)}")
    for name in sorted(n for n in names if n == "01" or n.startswith("invalid_")):
        print(f"  {name}")
    return copy_file_name


def reload_session(nwb_file_name: str) -> str:
    """Delete the file's Nwbfile entry (cascading to every table of that session), then register it."""
    entry = Nwbfile & {"nwb_file_name": get_nwb_copy_filename(nwb_file_name)}
    if entry:
        section(f"Deleting the existing entry for {nwb_file_name}")
        entry.delete(safemode=False)
    return ensure_session(nwb_file_name)


def report_insert_errors(copy_file_name: str) -> None:
    errors = InsertError & {"nwb_file_name": copy_file_name}
    print(f"InsertError rows: {len(errors)}")
    if errors:
        print(errors)
