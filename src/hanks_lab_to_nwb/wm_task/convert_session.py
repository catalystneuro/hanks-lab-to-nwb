"""Convert a single ToneCatDelayResp (working memory) session to NWB."""
import datetime
import os
import pickle
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from hanks_lab_to_nwb.utils import filter_optical_fibers_for_session, patch_fp_metadata_for_session
from hanks_lab_to_nwb.wm_task import WMNWBConverter

# Network-mounted .doric files require locking disabled for HDF5
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

# AIN channel → brain region, keyed by session ID (from Subj Info.txt)
_SESSION_AIN_TO_REGION = {
    119247: {1: "DLS", 2: "PL", 3: "DMS", 4: "NAc"},   # subj 400
    124770: {1: "DMS", 2: "DLS", 3: "TS",  4: "NAc"},   # subj 238
}


def session_to_nwb(
    sess_id: int,
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    stub_test: bool = False,
):
    """Convert one WM task session to NWB.

    Parameters
    ----------
    sess_id :
        Integer session ID, e.g. 119247. Used to locate all source files:
        Session_{session_id}.doric, fp_data_{session_id}.pkl,
        sess_data_{session_id}.pkl, mov_{session_id}.mp4
    data_dir_path :
        Directory containing all source files for this session.
    output_dir_path :
        Directory where the .nwb file will be written.
        Sub-directory "nwb_stub/" is used when stub_test=True.
    stub_test :
        If True, write only the first 100 samples of each time series.
    """
    data_dir_path = Path(data_dir_path)
    output_dir_path = Path(output_dir_path)
    if stub_test:
        output_dir_path = output_dir_path / "nwb_stub"
    output_dir_path.mkdir(parents=True, exist_ok=True)

    source_data = dict(
        DoricFP=dict(
            file_path=str(data_dir_path / f"Session_{sess_id}.doric"),
        ),
        FPProcessed=dict(
            fp_data_file_path=str(data_dir_path / f"fp_data_{sess_id}.pkl"),
        ),
        Behavior=dict(
            file_path=str(data_dir_path / f"sess_data_{sess_id}.pkl"),
        ),
        Video=dict(
            file_paths=[str(data_dir_path / f"mov_{sess_id}.mp4")],
        ),
    )
    conversion_options = dict(
        DoricFP=dict(stub_test=stub_test, timing_source="aligned_timestamps"),
        FPProcessed=dict(stub_test=stub_test),
        Behavior=dict(),
        Video=dict(),
    )

    converter = WMNWBConverter(source_data=source_data)
    metadata = converter.get_metadata()

    tz = ZoneInfo("America/Los_Angeles")  # TODO: confirm with Tanner (UC Davis)

    # session_start_time = when the Doric recording started (t=0 reference)
    # DoricFiberPhotometryInterface reads the Created attribute from the .doric file.
    doric_session_time = metadata["NWBFile"].get("session_start_time")
    if doric_session_time is not None:
        # Created attribute has no timezone — add local time zone
        if doric_session_time.tzinfo is None:
            doric_session_time = doric_session_time.replace(tzinfo=tz)
        session_start_time = doric_session_time
    else:
        # Fallback: derive from Bpod session date if Doric Created unparseable
        with open(data_dir_path / f"sess_data_{sess_id}.pkl", "rb") as f:
            sess_df_tmp = pickle.load(f)
        session_date = sess_df_tmp["sessiondate"].iloc[0]
        start_timedelta = sess_df_tmp["starttime"].iloc[0]
        session_start_time = (
            datetime.datetime(session_date.year, session_date.month, session_date.day)
            + start_timedelta
        ).replace(tzinfo=tz)

    # subject_id always comes from Bpod pkl
    with open(data_dir_path / f"sess_data_{sess_id}.pkl", "rb") as f:
        sess_df = pickle.load(f)
    subject_id = str(int(sess_df["subjid"].iloc[0]))

    metadata["NWBFile"]["session_start_time"] = session_start_time
    metadata["NWBFile"]["session_id"] = str(sess_id)

    editable_metadata = load_dict_from_file(Path(__file__).parent / "metadata.yaml")
    metadata = dict_deep_update(metadata, editable_metadata)

    # Shared FP hardware (models + instances) — single source of truth for both tasks
    fiber_photometry_metadata = load_dict_from_file(
        Path(__file__).parent.parent / "metadata" / "fiber_photometry.yaml"
    )
    metadata = dict_deep_update(metadata, fiber_photometry_metadata)

    metadata["Subject"]["subject_id"] = subject_id

    # Session-specific FP: filter optical fibers to session regions, add coords, patch table/series
    ain_to_region = _SESSION_AIN_TO_REGION[sess_id]
    fp_meta = metadata["Ophys"]["FiberPhotometry"]
    fp_interface = converter.data_interface_objects["FPProcessed"]
    filter_optical_fibers_for_session(fp_meta, ain_to_region, fp_interface.fp_data)
    patch_fp_metadata_for_session(fp_meta, ain_to_region)

    nwbfile_path = output_dir_path / f"sub-{subject_id}_ses-{sess_id}.nwb"

    converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        conversion_options=conversion_options,
        overwrite=True,
    )
    return nwbfile_path


if __name__ == "__main__":
    # Parameters for conversion
    sess_id = 119247
    data_dir_path = Path("/Users/weian/source_data/hanks-lab/For Catalyst Neuro")
    output_dir_path = Path("/Users/weian/catalystneuro/hanks-lab-to-nwb/nwb_output")
    stub_test = False

    nwbfile_path = session_to_nwb(
        sess_id=sess_id,
        data_dir_path=data_dir_path,
        output_dir_path=output_dir_path,
        stub_test=stub_test,
    )
    print(nwbfile_path)
