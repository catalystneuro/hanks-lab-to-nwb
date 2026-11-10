"""Session-specific patching of FP metadata loaded from fiber_photometry.yaml."""

# Keys produced by get_default_fiber_photometry_metadata. They are removed before writing so the
# placeholder scaffold devices do not appear in the NWB file alongside the real ones.
_PLACEHOLDER_DEVICE_MODEL_KEYS = {"optical_fiber_model", "excitation_source_model", "photodetector_model"}
_PLACEHOLDER_DEVICE_KEYS = {"optical_fiber", "excitation_source", "photodetector"}
_PLACEHOLDER_INDICATOR_KEYS = {"indicator"}
_PLACEHOLDER_ROW_KEYS = {"row0"}


def _fiber_note(recording_info: dict, region: str) -> str:
    """Note for one fiber's FiberPhotometryTable rows from the lab's per-fiber comment.

    ``recording_info`` is ``fp_data["fp_data"]``. ``comments`` is optional; returns an empty
    string when there is no comment for ``region``. The per-fiber ``fpids`` are not stored until
    the lab confirms what they identify.
    """
    comment = str((recording_info.get("comments") or {}).get(region) or "").strip()
    return f"Lab comment: {comment}" if comment else ""


def patch_fp_metadata_for_session(metadata: dict, ain_to_region: dict, fp_data: dict, region_names: dict) -> None:
    """Fill in the session-specific fields of the shared fiber photometry metadata.

    fiber_photometry.yaml contains all hardware metadata and the full FiberPhotometryTable row
    structure. This function patches what differs per session:

    1. Removes placeholder scaffold entries left by get_default_fiber_photometry_metadata.
    2. Sets ``location`` on each FiberPhotometryTable row from the AIN -> region mapping.
    3. Sets ``name`` and ``description`` on the per-AIN device instances: optical fibers get
       region-based names (e.g. ``optical_fiber_NAc``), excitation filters get AIN-based names
       (e.g. ``excitation_filter_isosbestic_AIN01``) because they belong to the channel's
       minicube, not to the implant.
    4. Sets ``fiber_insertion`` coordinates on each ``optical_fiber_ain0X`` device from
       ``fp_data["implant_info"]``. A region with no entry there gets no coordinates.
    5. Sets ``notes`` on the FiberPhotometryTable rows from the lab's per-fiber comment
       (``fp_data["fp_data"]["comments"]``). Skipped when a session has none.
    6. Replaces ``{regions}`` in every series' ``fiber_photometry_table_region_description``
       with the full names of the session's regions, in AIN order.

    Parameters
    ----------
    metadata :
        The full converter metadata dict, modified in place.
    ain_to_region :
        Mapping of AIN channel numbers to brain region abbreviations,
        e.g. {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"}.
    fp_data :
        The loaded fp_data_{session_id}.pkl dict, containing implant_info[region] with keys
        AP, ML, DV, side.
    region_names :
        Mapping of region abbreviation to full name, e.g. {"NAc": "Nucleus accumbens"}
        (``regions`` in metadata/sessions.yaml). A region missing from it keeps its abbreviation.
    """
    if "implant_info" not in fp_data:
        raise KeyError("'implant_info' not found in fp_data.")
    implant_info = fp_data["implant_info"]

    # 1. Remove placeholder scaffold so it doesn't pollute the NWB file.
    for key in _PLACEHOLDER_DEVICE_MODEL_KEYS:
        metadata.get("DeviceModels", {}).pop(key, None)
    for key in _PLACEHOLDER_DEVICE_KEYS:
        metadata.get("Devices", {}).pop(key, None)
    fp_meta = metadata["FiberPhotometry"]
    for key in _PLACEHOLDER_INDICATOR_KEYS:
        fp_meta.get("FiberPhotometryIndicators", {}).pop(key, None)
    table_rows = fp_meta["FiberPhotometryTable"]["rows"]
    for key in _PLACEHOLDER_ROW_KEYS:
        table_rows.pop(key, None)

    # 2, 3 & 4. Patch location, device names and descriptions, and fiber_insertion per AIN channel.
    devices = metadata["Devices"]
    for ain, region in ain_to_region.items():
        atlas_name = region_names.get(region, region)
        for row_prefix in ("iso", "sig"):
            row_key = f"{row_prefix}_ain0{ain}"
            table_rows[row_key]["location"] = atlas_name

        # Optical fibers are implanted per region, so they are named by region. Excitation
        # filters live in the minicube of a Doric channel (AIN01-02: iFMC5, AIN03-04: iFMC4)
        # and the region->AIN patching changes between sessions, so they are named by AIN,
        # like the photodetectors. Region-based filter names made one name describe different
        # filters in different sessions (see "Excitation filter naming" in conversion_notes.md).
        # Each description names the session's region (NWB Inspector flags devices with no
        # description).
        devices[f"optical_fiber_ain0{ain}"]["name"] = f"optical_fiber_{region}"
        devices[f"optical_fiber_ain0{ain}"][
            "description"
        ] = f"Optical fiber implanted in {atlas_name} ({region}), recorded on AIN0{ain}."
        devices[f"excitation_filter_isosbestic_ain0{ain}"]["name"] = f"excitation_filter_isosbestic_AIN0{ain}"
        devices[f"excitation_filter_isosbestic_ain0{ain}"][
            "description"
        ] = f"Isosbestic excitation bandpass filter for the {atlas_name} ({region}) channel, AIN0{ain}."
        devices[f"excitation_filter_signal_ain0{ain}"]["name"] = f"excitation_filter_signal_AIN0{ain}"
        devices[f"excitation_filter_signal_ain0{ain}"][
            "description"
        ] = f"Signal excitation bandpass filter for the {atlas_name} ({region}) channel, AIN0{ain}."

        info = implant_info.get(region, {})
        if info:
            devices[f"optical_fiber_ain0{ain}"]["fiber_insertion"] = dict(
                insertion_position_ap_in_mm=float(info["AP"]),
                insertion_position_ml_in_mm=float(info["ML"]),
                insertion_position_dv_in_mm=float(info["DV"]),
                position_reference="bregma",
                hemisphere=info["side"],
            )

    # 5. Notes from the lab's comment per fiber. `notes` is an optional table column,
    # so once any row has one, every row gets a value (empty where a fiber has none).
    recording_info = fp_data.get("fp_data") or {}
    notes = {ain: _fiber_note(recording_info, region) for ain, region in ain_to_region.items()}
    if any(notes.values()):
        for row_key, row in table_rows.items():
            ain = int(row_key.rsplit("ain", 1)[1])
            row["notes"] = notes.get(ain, "")

    # 6. Name the session's regions in each series' table region description.
    regions = ", ".join(region_names.get(ain_to_region[ain], ain_to_region[ain]) for ain in sorted(ain_to_region))
    for series_metadata in fp_meta.values():
        if "fiber_photometry_table_region_description" in series_metadata:
            series_metadata["fiber_photometry_table_region_description"] = series_metadata[
                "fiber_photometry_table_region_description"
            ].format(regions=regions)
