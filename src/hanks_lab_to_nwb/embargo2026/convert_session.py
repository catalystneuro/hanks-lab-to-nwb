"""Convert a single Hanks lab session (WM or bandit task) to NWB."""

import datetime
import pickle
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from hanks_lab_to_nwb.embargo2026 import HanksLabNWBConverter
from hanks_lab_to_nwb.utils import patch_fp_metadata_for_session

_METADATA_DIR = Path(__file__).parent / "metadata"

# Per-session and per-subject values (task, AIN channel -> brain region, subject details, time zone)
# live in this file. Edit it to add a session; see the comments inside.
SESSIONS_FILE_PATH = _METADATA_DIR / "sessions.yaml"

# Processed signal registry: (converter_key, pkl_signal_key, metadata_key)
_PROCESSED_SIGNALS = [
    ("ProcessedFP_RawIso", "raw_iso", "raw_iso_series"),
    ("ProcessedFP_RawLig", "raw_lig", "raw_lig_series"),
    ("ProcessedFP_FilteredIso", "filtered_iso", "filtered_iso_series"),
    ("ProcessedFP_FilteredLig", "filtered_lig", "filtered_lig_series"),
    ("ProcessedFP_FittedIso", "fitted_iso", "fitted_iso_series"),
    ("ProcessedFP_BaselineIso", "baseline_iso", "baseline_iso_series"),
    ("ProcessedFP_BaselineLig", "baseline_lig", "baseline_lig_series"),
    ("ProcessedFP_BaselineCorrIso", "baseline_corr_iso", "baseline_corr_iso_series"),
    ("ProcessedFP_BaselineCorrLig", "baseline_corr_lig", "baseline_corr_lig_series"),
    ("ProcessedFP_FittedBaselineFbandIso", "fitted_baseline_fband_iso", "fitted_baseline_fband_iso_series"),
    ("ProcessedFP_DFF", "dff_iso", "dff_series"),
    ("ProcessedFP_DFFBaselineFband", "dff_iso_baseline_fband", "dff_baseline_fband_series"),
]


def load_session_registry() -> dict:
    """Return the session registry stored in metadata/sessions.yaml.

    Keys: ``timezone``, ``tasks`` (task name -> Bpod protocol), ``subjects`` (subject ID -> sex,
    strain, date of birth, weight) and ``sessions`` (session ID -> task and AIN channel -> region).
    """
    return load_dict_from_file(SESSIONS_FILE_PATH)


def session_to_nwb(
    session_id: int,
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    stub_test: bool = False,
):
    """Convert one Hanks lab session to NWB.

    Writes the Bpod behavior, the processed fiber photometry series and their artifact windows,
    plus the raw fiber photometry acquisition when ``Session_{session_id}.doric`` is present and
    the behavior video when ``mov_{session_id}.mp4`` is present.

    Parameters
    ----------
    session_id :
        Integer session ID (e.g. 119974). Used to locate Session_{session_id}.doric,
        fp_data_{session_id}.pkl, sess_data_{session_id}.pkl and mov_{session_id}.mp4.
        The session and its subject must be registered in metadata/sessions.yaml.
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

    # Look the session up in the registry before reading any large file, so a session that was
    # not registered fails immediately with a message saying what to add.
    registry = load_session_registry()
    if session_id not in registry["sessions"]:
        raise ValueError(f"Session {session_id} is not registered. Add it under 'sessions' in {SESSIONS_FILE_PATH}.")
    session_info = registry["sessions"][session_id]
    ain_to_region = session_info["ain_to_region"]
    task_type = session_info["task"]
    timezone = ZoneInfo(registry["timezone"])

    with open(data_dir_path / f"sess_data_{session_id}.pkl", "rb") as f:
        sess_df = pickle.load(f)

    subject_id = int(sess_df["subjid"].iloc[0])
    if subject_id not in registry["subjects"]:
        raise ValueError(
            f"Subject {subject_id} of session {session_id} is not registered. "
            f"Add it under 'subjects' in {SESSIONS_FILE_PATH}."
        )
    subject_metadata = dict(registry["subjects"][subject_id])
    subject_metadata["date_of_birth"] = datetime.datetime.fromisoformat(subject_metadata["date_of_birth"]).replace(
        tzinfo=timezone
    )

    protocol = sess_df["protocol"].iloc[0]
    expected_protocol = registry["tasks"][task_type]["protocol"]
    if protocol != expected_protocol:
        raise ValueError(
            f"Session {session_id} is registered as '{task_type}' (Bpod protocol '{expected_protocol}') but "
            f"sess_data_{session_id}.pkl was recorded with protocol '{protocol}'. "
            f"Correct the session's task in {SESSIONS_FILE_PATH}."
        )

    _fp_yaml = load_dict_from_file(_METADATA_DIR / "fiber_photometry.yaml")
    _video_yaml = load_dict_from_file(_METADATA_DIR / "video.yaml")
    _external_resources_yaml = load_dict_from_file(_METADATA_DIR / "external_resources.yaml")
    iso_streams = _fp_yaml["FiberPhotometry"]["isosbestic_series"]["stream_names"]
    sig_streams = _fp_yaml["FiberPhotometry"]["signal_series"]["stream_names"]

    doric_path = data_dir_path / f"Session_{session_id}.doric"
    sess_data_path = str(data_dir_path / f"sess_data_{session_id}.pkl")
    fp_data_path = str(data_dir_path / f"fp_data_{session_id}.pkl")
    video_path = data_dir_path / f"mov_{session_id}.mp4"
    source_data = dict(
        Behavior=dict(file_path=sess_data_path, fp_data_path=fp_data_path),
    )
    conversion_options = dict()
    # The raw lock-in acquisition is only available for sessions whose .doric was
    # shared; processed FP (from the pkl) and behavior are converted regardless.
    if doric_path.exists():
        source_data["DoricFPIsosbestic"] = dict(
            file_path=str(doric_path), stream_names=iso_streams, metadata_key="isosbestic_series"
        )
        source_data["DoricFPSignal"] = dict(
            file_path=str(doric_path), stream_names=sig_streams, metadata_key="signal_series"
        )
        conversion_options["DoricFPIsosbestic"] = dict(stub_test=stub_test)
        conversion_options["DoricFPSignal"] = dict(stub_test=stub_test)
    # Spyglass reads the video through the epoch and task table, which span the video's frames.
    if video_path.exists():
        source_data["Video"] = dict(
            file_path=video_path,
            timestamps_file_path=video_path.with_suffix(".doric"),
            metadata_key="behavior_video",
            video_name="BehaviorVideo",
        )
        source_data["Epoch"] = dict(file_path=video_path.with_suffix(".doric"))
    for interface_name, signal_key, meta_key in _PROCESSED_SIGNALS:
        source_data[interface_name] = dict(
            file_path=fp_data_path,
            ain_to_region=ain_to_region,
            signal_key=signal_key,
            metadata_key=meta_key,
        )
        conversion_options[interface_name] = dict(stub_test=stub_test, parent_container="processing/ophys")

    # Artifact windows reference the processed series, so this interface needs to resolve
    # each pkl signal key to the series name configured in fiber_photometry.yaml.
    source_data["FiberPhotometryArtifacts"] = dict(
        file_path=fp_data_path,
        ain_to_region=ain_to_region,
        signal_key_to_metadata_key={signal_key: meta_key for _, signal_key, meta_key in _PROCESSED_SIGNALS},
    )

    converter = HanksLabNWBConverter(source_data=source_data)
    metadata = converter.get_metadata()

    session_start_time = metadata["NWBFile"]["session_start_time"]
    if session_start_time.tzinfo is None:
        metadata["NWBFile"]["session_start_time"] = session_start_time.replace(tzinfo=timezone)

    metadata["NWBFile"]["session_id"] = str(session_id)

    task_metadata = load_dict_from_file(_METADATA_DIR / f"{task_type}.yaml")
    metadata = dict_deep_update(metadata, task_metadata)
    # camera_id is the ID in the camera's name in video.yaml ("camera_device 0").
    metadata["Tasks"][0]["name"] = protocol
    metadata["Tasks"][0]["camera_id"] = [0]

    metadata = dict_deep_update(metadata, _fp_yaml, append_list=False)
    metadata = dict_deep_update(metadata, _video_yaml)
    # Ontology terms (HERD); run_conversion writes them under /general/external_resources.
    metadata = dict_deep_update(metadata, _external_resources_yaml)

    metadata["Subject"]["subject_id"] = str(subject_id)
    metadata["Subject"].update(subject_metadata)

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
    session_id = 119247
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
