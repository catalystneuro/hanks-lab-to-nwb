"""Convert a single Hanks lab session (WM or bandit task) to NWB."""

import datetime
import pickle
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from hanks_lab_to_nwb.embargo2026 import HanksLabNWBConverter
from hanks_lab_to_nwb.utils import patch_fp_metadata_for_session

_TZ = ZoneInfo("America/Los_Angeles")

# AIN channel → brain region per session (from Subj Info.txt)
_SESSION_AIN_TO_REGION = {
    119247: {1: "DLS", 2: "PL", 3: "DMS", 4: "NAc"},  # subj 400, WM
    119974: {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"},  # subj 400, Bandit
    124770: {1: "DMS", 2: "DLS", 3: "TS", 4: "NAc"},  # subj 238, WM
    124949: {1: "NAc", 2: "DMS", 3: "TS", 4: "DLS"},  # subj 238, Bandit
}

# session → task-specific metadata YAML (determines session_description and keywords)
_SESSION_TASK_TYPE = {
    119247: "wm_task",
    119974: "bandit_task",
    124770: "wm_task",
    124949: "bandit_task",
}

_SUBJECT_METADATA = {
    400: dict(
        sex="M",
        strain="Long Evans",
        date_of_birth=datetime.datetime(2024, 3, 19, tzinfo=_TZ),
        weight="530 g",
    ),
    238: dict(
        sex="M",
        strain="Long Evans",
        # TODO: confirm exact date — lab reported "2025-05-0" (likely 2025-05-01)
        date_of_birth=datetime.datetime(2025, 5, 1, tzinfo=_TZ),
        weight="540 g",
    ),
}


def session_to_nwb(
    session_id: int,
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    stub_test: bool = False,
):
    """Convert one Hanks lab session to NWB (FP raw data only).

    Parameters
    ----------
    session_id :
        Integer session ID (e.g. 119974). Must be in _SESSION_AIN_TO_REGION.
        Used to locate Session_{session_id}.doric, fp_data_{session_id}.pkl,
        and sess_data_{session_id}.pkl.
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

    _metadata_dir = Path(__file__).parent / "metadata"
    _fp_yaml = load_dict_from_file(_metadata_dir / "fiber_photometry.yaml")
    iso_streams = _fp_yaml["FiberPhotometry"]["isosbestic_series"]["stream_names"]
    sig_streams = _fp_yaml["FiberPhotometry"]["signal_series"]["stream_names"]

    doric_path = str(data_dir_path / f"Session_{session_id}.doric")
    source_data = dict(
        DoricFPIsosbestic=dict(file_path=doric_path, stream_names=iso_streams, metadata_key="isosbestic_series"),
        DoricFPSignal=dict(file_path=doric_path, stream_names=sig_streams, metadata_key="signal_series"),
    )
    conversion_options = dict(
        DoricFPIsosbestic=dict(stub_test=stub_test),
        DoricFPSignal=dict(stub_test=stub_test),
    )

    converter = HanksLabNWBConverter(source_data=source_data)
    metadata = converter.get_metadata()

    session_start_time = metadata["NWBFile"]["session_start_time"]
    if session_start_time.tzinfo is None:
        metadata["NWBFile"]["session_start_time"] = session_start_time.replace(tzinfo=_TZ)

    with open(data_dir_path / f"sess_data_{session_id}.pkl", "rb") as f:
        sess_df = pickle.load(f)
    subject_id = str(int(sess_df["subjid"].iloc[0]))

    metadata["NWBFile"]["session_id"] = str(session_id)

    task_type = _SESSION_TASK_TYPE[session_id]
    task_metadata = load_dict_from_file(_metadata_dir / f"{task_type}.yaml")
    metadata = dict_deep_update(metadata, task_metadata)

    metadata = dict_deep_update(metadata, _fp_yaml, append_list=False)

    metadata["Subject"]["subject_id"] = subject_id
    metadata["Subject"].update(_SUBJECT_METADATA[int(subject_id)])

    ain_to_region = _SESSION_AIN_TO_REGION[session_id]
    with open(data_dir_path / f"fp_data_{session_id}.pkl", "rb") as f:
        fp_data = pickle.load(f)
    patch_fp_metadata_for_session(metadata, ain_to_region, fp_data)

    nwbfile_path = output_dir_path / f"sub-{subject_id}_ses-{session_id}.nwb"

    converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        conversion_options=conversion_options,
        overwrite=True,
    )
    return nwbfile_path


if __name__ == "__main__":
    session_id = 119974
    data_dir_path = Path("/Users/weian/source_data/hanks-lab/For Catalyst Neuro")
    output_dir_path = Path("/Users/weian/catalystneuro/hanks-lab-to-nwb/nwb_output")
    stub_test = False

    nwbfile_path = session_to_nwb(
        session_id=session_id,
        data_dir_path=data_dir_path,
        output_dir_path=output_dir_path,
        stub_test=stub_test,
    )
    print(nwbfile_path)
