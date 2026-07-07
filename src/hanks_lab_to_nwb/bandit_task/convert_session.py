"""Convert a single ClassicRLTasks (bandit) session to NWB."""
import pickle
from pathlib import Path
from zoneinfo import ZoneInfo

from neuroconv.utils import dict_deep_update, load_dict_from_file

from hanks_lab_to_nwb.converters import HanksLabNWBConverter

# Network-mounted .doric files require locking disabled for HDF5
# os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

# AIN channel → brain region, keyed by session ID (from Subj Info.txt)
_SESSION_AIN_TO_REGION = {
    119974: {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"},   # subj 400
    124949: {1: "NAc", 2: "DMS", 3: "TS",  4: "DLS"},   # subj 238
}

# AOUT wavelength (nm) — used by patch function for descriptions
_AOUT_WAVELENGTH_NM = {1: 420, 2: 490, 3: 415, 4: 490}


def _build_fp_session_metadata(sess_id: int, fp_data: dict) -> dict:
    """Build the session-specific FiberPhotometry metadata block.

    Returns OpticalFibers with implant coordinates from the fp_data pkl.
    FiberPhotometryTable and FiberPhotometryResponseSeries are loaded from
    fiber_photometry.yaml and patched by _patch_fp_metadata_for_session.
    """
    ain_to_region = _SESSION_AIN_TO_REGION[sess_id]
    implant_info = fp_data["implant_info"]

    optical_fibers = []
    seen_regions = set()
    for ain in range(1, 5):
        region = ain_to_region[ain]
        if region in seen_regions:
            continue
        seen_regions.add(region)
        info = implant_info[region]
        optical_fibers.append(
            dict(
                name=f"OpticalFiber_{region}",
                description=f"400 μm flat optical fiber implanted in {region}",
                model="DoricFlatFiber400um",
                fiber_insertion=dict(
                    insertion_position_ap_in_mm=float(info["AP"]),
                    insertion_position_ml_in_mm=float(info["ML"]),
                    insertion_position_dv_in_mm=float(info["DV"]),
                    position_reference="bregma",
                    hemisphere=info["side"],
                ),
            )
        )

    return dict(OpticalFibers=optical_fibers)


def _patch_fp_metadata_for_session(fp_meta: dict, sess_id: int) -> None:
    """Fill in session-specific region names in the shared FP metadata.

    Patches `location` and `optical_fiber` in each FiberPhotometryTable row,
    and updates series `name` and `description` with the actual brain region,
    derived from the AIN channel number embedded in each row's `photodetector`
    field and each series' `stream_name`.
    """
    ain_to_region = _SESSION_AIN_TO_REGION[sess_id]

    for row in fp_meta["FiberPhotometryTable"]["rows"]:
        ain_num = int(row["photodetector"].replace("PhotodetectorAIN", ""))
        region = ain_to_region[ain_num]
        row["location"] = region
        row["optical_fiber"] = f"OpticalFiber_{region}"

    for series in fp_meta["FiberPhotometryResponseSeries"]:
        stream = series["stream_name"]
        ain_num = int(stream.split("_AIN")[1])
        aout_num = int(stream.split("_LockInAOUT")[1].split("_")[0])
        region = ain_to_region[ain_num]
        wl = _AOUT_WAVELENGTH_NM[aout_num]
        is_iso = wl != 490
        series["name"] = f"FPResponseSeries_{region}_{wl}nm"
        series["description"] = (
            f"dLight3.8 {'isosbestic control' if is_iso else 'dopamine signal'} "
            f"from {region} at {wl} nm, acquired via lock-in detection"
        )
        series["fiber_photometry_table_region_description"] = (
            f"FiberPhotometryTable: {region} @ {wl} nm "
            f"({'isosbestic' if is_iso else 'signal'})"
        )


def session_to_nwb(
    session_id: int,
    data_dir_path: str | Path,
    output_dir_path: str | Path,
    stub_test: bool = False,
):
    """Convert one bandit task session to NWB.

    Parameters
    ----------
    session_id :
        Integer session ID, e.g. 119974. Used to locate all source files:
        Session_{sess_id}.doric, fp_data_{sess_id}.pkl,
        sess_data_{sess_id}.pkl, mov_{sess_id}.mp4
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
            file_path=str(data_dir_path / f"Session_{session_id}.doric"),
        ),
    )
    conversion_options = dict(
        DoricFP=dict(stub_test=stub_test, timing_source="aligned_timestamps"),
    )

    converter = HanksLabNWBConverter(source_data=source_data)
    metadata = converter.get_metadata()

    # session_start_time = when the Doric recording started (t=0 reference)
    session_start_time = metadata["NWBFile"]["session_start_time"]
    if session_start_time.tzinfo is None:
        tz = ZoneInfo("America/Los_Angeles")  # TODO: confirm with Tanner (UC Davis)
        metadata["NWBFile"]["session_start_time"] = session_start_time.replace(tzinfo=tz)

    with open(data_dir_path / f"sess_data_{session_id}.pkl", "rb") as f:
        sess_df = pickle.load(f)
    subject_id = str(int(sess_df["subjid"].iloc[0]))

    metadata["NWBFile"]["session_id"] = str(session_id).replace("_", "-")

    editable_metadata = load_dict_from_file(Path(__file__).parent / "metadata.yaml")
    metadata = dict_deep_update(metadata, editable_metadata)

    # Shared FP hardware (models + instances) — single source of truth for both tasks
    fiber_photometry_metadata = load_dict_from_file(
        Path(__file__).parent.parent / "metadata" / "fiber_photometry.yaml"
    )
    metadata = dict_deep_update(metadata, fiber_photometry_metadata)

    metadata["Subject"]["subject_id"] = subject_id

    # Session-specific FP: OpticalFibers (coords from pkl) + patch table/series with regions
    fp_data_file_path = str(data_dir_path / f"fp_data_{session_id}.pkl")
    with open(fp_data_file_path, "rb") as f:
        fp_data = pickle.load(f)
    fp_session_meta = _build_fp_session_metadata(session_id, fp_data)
    metadata["Ophys"]["FiberPhotometry"].update(fp_session_meta)
    _patch_fp_metadata_for_session(metadata["Ophys"]["FiberPhotometry"], session_id)

    nwbfile_path = output_dir_path / f"sub-{subject_id}_ses-{session_id}.nwb"

    converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=metadata,
        conversion_options=conversion_options,
        overwrite=True,
    )
    return nwbfile_path


if __name__ == "__main__":
    # Parameters for conversion
    session_id = 119974
    data_dir_path = Path("/Users/weian/source_data/hanks-lab/For Catalyst Neuro")
    output_dir_path = Path("/Users/weian/catalystneuro/hanks-lab-to-nwb/nwb_output")
    stub_test = True

    session_to_nwb(
        session_id=session_id,
        data_dir_path=data_dir_path,
        output_dir_path=output_dir_path,
        stub_test=stub_test,
    )
