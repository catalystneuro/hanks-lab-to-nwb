"""Session-specific patching of FP metadata loaded from fiber_photometry.yaml."""

# Keys produced by get_default_fiber_photometry_metadata — removed before write
# so placeholder scaffold devices don't appear in the NWB file alongside real ones.
# Allen Mouse Brain Atlas full region names, keyed by lab abbreviation.
# DLS/DMS are informal subdivisions of the Allen "Caudoputamen" (CP) structure.
_ATLAS_REGION_NAME = {
    "NAc": "Nucleus accumbens",
    "DLS": "Dorsolateral striatum",
    "DMS": "Dorsomedial striatum",
    "PL": "Prelimbic area",
    "TS": "Tail of striatum",
}

_PLACEHOLDER_DEVICE_MODEL_KEYS = {"optical_fiber_model", "excitation_source_model", "photodetector_model"}
_PLACEHOLDER_DEVICE_KEYS = {"optical_fiber", "excitation_source", "photodetector"}
_PLACEHOLDER_INDICATOR_KEYS = {"indicator"}
_PLACEHOLDER_ROW_KEYS = {"row0"}


def patch_fp_metadata_for_session(metadata: dict, ain_to_region: dict, fp_data: dict) -> None:
    """Fill in the three session-specific fields in the shared FP metadata.

    The fiber_photometry.yaml contains all hardware metadata and the full
    FiberPhotometryTable row structure. This function only patches what differs
    per session/subject:

    1. Removes placeholder scaffold entries left by get_default_fiber_photometry_metadata.
    2. Sets ``location`` on each of the 8 pre-defined FiberPhotometryTable rows
       from the AIN→region mapping.
    3. Sets ``name`` on per-AIN device instances to region-based names
       (e.g. ``optical_fiber_NAc``, ``excitation_filter_isosbestic_NAc``).
    4. Sets ``fiber_insertion`` coordinates on each ``optical_fiber_ain0X`` device
       from ``fp_data["implant_info"]``.
    5. Sets ``fiber_photometry_table_region_description`` on the two response series.

    Parameters
    ----------
    metadata :
        The full converter metadata dict — modified in-place.
    ain_to_region :
        Mapping of AIN channel numbers to brain region names,
        e.g. {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"}.
    fp_data :
        The loaded fp_data_{sessid}.pkl dict containing
        implant_info[region] with keys AP, ML, DV, side.
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

    # 2, 3 & 4. Patch location, fiber_insertion, and region-based device names per AIN channel.
    devices = metadata["Devices"]
    for ain, region in ain_to_region.items():
        atlas_name = _ATLAS_REGION_NAME.get(region, region)
        for row_prefix in ("iso", "sig"):
            row_key = f"{row_prefix}_ain0{ain}"
            table_rows[row_key]["location"] = atlas_name

        # Rename device instances from AIN-indexed to region-named.
        devices[f"optical_fiber_ain0{ain}"]["name"] = f"optical_fiber_{region}"
        devices[f"excitation_filter_isosbestic_ain0{ain}"]["name"] = f"excitation_filter_isosbestic_{region}"
        devices[f"excitation_filter_signal_ain0{ain}"]["name"] = f"excitation_filter_signal_{region}"

        info = implant_info.get(region, {})
        if info:
            devices[f"optical_fiber_ain0{ain}"]["fiber_insertion"] = dict(
                insertion_position_ap_in_mm=float(info["AP"]),
                insertion_position_ml_in_mm=float(info["ML"]),
                insertion_position_dv_in_mm=float(info["DV"]),
                position_reference="bregma",
                hemisphere=info["side"],
            )

    # 4. Set region-aware descriptions on the two response series.
    regions = [_ATLAS_REGION_NAME.get(ain_to_region[ain], ain_to_region[ain]) for ain in sorted(ain_to_region)]
    regions_str = ", ".join(regions)
    fp_meta["isosbestic_series"][
        "fiber_photometry_table_region_description"
    ] = f"Isosbestic control from {regions_str} at ~415/420 nm (columns follow AIN01-04 order)"
    fp_meta["signal_series"][
        "fiber_photometry_table_region_description"
    ] = f"dLight3.8 dopamine signal from {regions_str} at 490 nm (columns follow AIN01-04 order)"
