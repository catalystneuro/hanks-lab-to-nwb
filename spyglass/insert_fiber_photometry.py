"""Scoped ingestion: fiber photometry ONLY, for one or more converted Hanks NWB files.

Unlike `sgi.insert_sessions()` (which unconditionally calls `populate_all_common()` and
runs every common table -- VideoFile, ImportedPose, ImportedLFP, VirusInjection,
OpticalFiberImplant, OptogeneticProtocol, PositionSource, StateScriptFile, TaskEpoch,
SampleCount, SensorData, RawPosition, Probe/Electrode -- relying on raise_err=False to
paper over whichever ones break), this script inserts ONLY:

  - the parents fiber photometry's foreign keys require: Institution, Lab, LabMember,
    LabTeam, Subject (for Session) and the photometry device catalog (Indicator,
    ExcitationSource, Photodetector, DichroicMirror, OpticalFilter, OpticalFiber);
  - Session, Session.Experimenter (unavoidable: FiberPhotometryConfig and
    FiberPhotometryResponseSeries both declare `-> Session`);
  - FiberPhotometryConfig, FiberPhotometryResponseSeries (the actual target).

Behavior (Bpod trials/states), video and artifact intervals stay in the NWB file.

Uses Spyglass's own mechanics:
  - the copy+register step is the same two lines `insert_sessions()` runs before calling
    populate_all_common();
  - the per-table inserts go through Spyglass's own
    `spyglass.common.populate_all_common.single_transaction_make()` helper, with a trimmed
    `tables` list, grouped/ordered the same way populate_all_common() does.

Arguments are either file names already in the Spyglass raw dir, or paths to converted
NWB files anywhere on disk (those are symlinked into the raw dir, not copied):

    conda activate spyglass-photometry
    cd spyglass
    python insert_fiber_photometry.py ../nwb_output/sub-238_ses-124770.nwb [...]
"""

import sys
from pathlib import Path

import datajoint as dj

CONF = Path(__file__).with_name("dj_local_conf.json")

dj.config.load(str(CONF))  # BEFORE any spyglass import
dj.conn(use_tls=False)

from spyglass.common.common_lab import (  # noqa: E402
    Institution,
    Lab,
    LabMember,
    LabTeam,
)
from spyglass.common.common_nwbfile import Nwbfile  # noqa: E402
from spyglass.common.common_photometry import (  # noqa: E402
    DichroicMirror,
    ExcitationSource,
    FiberPhotometryConfig,
    FiberPhotometryResponseSeries,
    Indicator,
    OpticalFiber,
    OpticalFilter,
    Photodetector,
)
from spyglass.common.common_region import BrainRegion  # noqa: E402
from spyglass.common.common_session import Session  # noqa: E402
from spyglass.common.common_subject import Subject  # noqa: E402
from spyglass.common.common_usage import InsertError  # noqa: E402
from spyglass.common.populate_all_common import single_transaction_make  # noqa: E402
from spyglass.data_import.insert_sessions import copy_nwb_link_raw_ephys  # noqa: E402
from spyglass.settings import raw_dir  # noqa: E402
from spyglass.utils.nwb_helper_fn import get_nwb_copy_filename  # noqa: E402

# Excluded on purpose (never imported, never called -- not caught-and-ignored):
# VideoFile, ImportedPose, ImportedLFP, VirusInjection, OpticalFiberImplant,
# OptogeneticProtocol, PositionSource, StateScriptFile, TaskEpoch, SampleCount,
# SensorData, RawPosition, Probe/Probe.Shank/Probe.Electrode, DataAcquisitionDevice*,
# CameraDevice, ProbeType, OpticalFiberDevice, Virus.
TABLE_GROUPS = [
    [  # parents Session's and FiberPhotometryConfig's FKs require
        Institution,
        Lab,
        LabMember,
        LabTeam,
        Subject,
        Indicator,
        ExcitationSource,
        Photodetector,
        DichroicMirror,
        OpticalFilter,
        OpticalFiber,
    ],
    [  # Session: FiberPhotometryConfig/ResponseSeries both declare `-> Session`
        Session,
        Session.Experimenter,
    ],
    [  # the actual target
        FiberPhotometryConfig,
        FiberPhotometryResponseSeries,
    ],
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


def insert_one(nwb_file_name: str) -> None:
    nwbfile_path = Path(raw_dir) / nwb_file_name
    if not nwbfile_path.exists():
        raise FileNotFoundError(f"Expected NWB file at {nwbfile_path}")

    out_nwb_file_name = get_nwb_copy_filename(nwb_file_name)
    copy_dict = {"nwb_file_name": out_nwb_file_name}

    # Idempotent: Nwbfile is keyed on the COPY filename (stem + "_.nwb"), not the original.
    entry = Nwbfile() & copy_dict
    if entry:
        section("Cleaning up existing Nwbfile entry from a previous run")
        entry.delete(safemode=False)

    section(f"STEP 1: copy + register (mirrors insert_sessions()): {nwb_file_name}")
    copy_nwb_link_raw_ephys(nwb_file_name, out_nwb_file_name)
    Nwbfile().insert_from_relative_file_name(out_nwb_file_name)
    print(f"Nwbfile rows for this copy: {len(Nwbfile() & copy_dict)}")

    section("STEP 2: single_transaction_make() over the trimmed, photometry-only table groups")
    error_constants = dict(
        dj_user=dj.config["database.user"],
        connection_id=dj.conn().connection_id,
        nwb_file_name=out_nwb_file_name,
    )
    for tables in TABLE_GROUPS:
        single_transaction_make(
            tables=tables,
            nwb_file_name=out_nwb_file_name,
            raise_err=True,  # nothing here is expected to fail; surface it loudly if it does
            error_constants=error_constants,
            # single_transaction_make()'s body does config.get(...) unconditionally --
            # the `config: dict = None` default is not None-safe.
            config={},
        )

    section("STEP 3: row counts")
    print(f"{'Session':<40} {len(Session() & copy_dict)} row(s)")
    print(f"{'Subject (whole DB)':<40} {len(Subject())} row(s)")
    for table in (Indicator, ExcitationSource, Photodetector, DichroicMirror, OpticalFilter, OpticalFiber):
        print(f"{table.__name__:<40} {len(table())} row(s)  (shared catalog, whole-table count)")
    print(f"{'BrainRegion':<40} {len(BrainRegion())} row(s)  (shared catalog, whole-table count)")
    cfg = FiberPhotometryConfig() & copy_dict
    rs = FiberPhotometryResponseSeries() & copy_dict
    fib = FiberPhotometryResponseSeries.Fiber() & copy_dict
    print(f"{'FiberPhotometryConfig':<40} {len(cfg)} row(s)")
    print(f"{'FiberPhotometryResponseSeries':<40} {len(rs)} row(s)")
    print(f"{'FiberPhotometryResponseSeries.Fiber':<40} {len(fib)} row(s)")

    section("STEP 4: InsertError log for this file")
    errs = InsertError() & {"nwb_file_name": out_nwb_file_name}
    print(f"InsertError rows: {len(errs)}")
    if errs:
        print(errs)

    section("STEP 5: table contents")
    print(
        (cfg * BrainRegion).proj(
            "region_name",
            "optical_fiber_name",
            "excitation_source_name",
            "photodetector_name",
            "excitation_filter_name",
            "excitation_wavelength_in_nm",
            "hemisphere",
            "ap_location",
            "ml_location",
            "dv_location",
        )
    )
    print(rs.proj("name", "num_samples", "unit"))

    section("STEP 6: read-back sanity check via Spyglass accessor")
    for key in rs.fetch("KEY"):
        df = (FiberPhotometryResponseSeries() & key).fetch1_dataframe()
        name = (FiberPhotometryResponseSeries() & key).fetch1("name")
        print(f"  {name!r}: shape={df.shape}, columns={list(df.columns)}")
        print(f"    t[0]={df.index[0]:.4f}  t[-1]={df.index[-1]:.4f}")

    section(f"DONE: {nwb_file_name}")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python insert_fiber_photometry.py NWB_FILE [NWB_FILE ...]")
    for nwb_file in sys.argv[1:]:
        insert_one(stage_in_raw_dir(nwb_file))


if __name__ == "__main__":
    main()
