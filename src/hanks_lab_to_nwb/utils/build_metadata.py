"""Session-specific patching of FP metadata loaded from fiber_photometry.yaml."""

# Keys produced by get_default_fiber_photometry_metadata — removed before write
# so placeholder scaffold devices don't appear in the NWB file alongside real ones.
# Allen Mouse Brain Atlas full region names, keyed by lab abbreviation.
# DLS/DMS are informal subdivisions of the Allen "Caudoputamen" (CP) structure.
# Description template for each response series' fiber_photometry_table_region_description.
# {regions_str} is replaced at runtime with the comma-separated region names for this session.
_SERIES_REGION_DESCRIPTION_TEMPLATES = {
    # Raw acquisition series (from .doric, ~6024 Hz)
    "isosbestic_series": "Isosbestic control signal for {regions_str} at ~415/420 nm",
    "signal_series": "dLight3.8 dopamine signal rows for {regions_str} at 490 nm (columns follow AIN01-04 order)",
    # Processed series (from fp_data pkl, ~200 Hz)
    "raw_iso_series": "Decimated isosbestic control signal for {regions_str}",
    "raw_lig_series": "Decimated signal rows for {regions_str} (columns follow AIN01-04 order)",
    "filtered_iso_series": "Filtered isosbestic rows for {regions_str} (columns follow AIN01-04 order)",
    "filtered_lig_series": "Filtered signal rows for {regions_str} (columns follow AIN01-04 order)",
    "fitted_iso_series": "Fitted isosbestic rows for {regions_str} (columns follow AIN01-04 order)",
    "baseline_iso_series": "Baseline isosbestic rows for {regions_str} (columns follow AIN01-04 order)",
    "baseline_lig_series": "Baseline signal rows for {regions_str} (columns follow AIN01-04 order)",
    "baseline_corr_iso_series": "Baseline-corrected isosbestic rows for {regions_str} (columns follow AIN01-04 order)",
    "baseline_corr_lig_series": "Baseline-corrected signal rows for {regions_str} (columns follow AIN01-04 order)",
    "fitted_baseline_fband_iso_series": "Freq-band fitted isosbestic rows for {regions_str} (columns follow AIN01-04 order)",
    "dff_series": "dLight3.8 dFF rows for {regions_str} (columns follow AIN01-04 order)",
    "dff_baseline_fband_series": "Frequency-band corrected DF/F trace for {regions_str}",
}

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

    # 4. Set region-aware descriptions on all response series.
    regions = [_ATLAS_REGION_NAME.get(ain_to_region[ain], ain_to_region[ain]) for ain in sorted(ain_to_region)]
    regions_str = ", ".join(regions)
    for meta_key, template in _SERIES_REGION_DESCRIPTION_TEMPLATES.items():
        fp_meta[meta_key]["fiber_photometry_table_region_description"] = template.format(regions_str=regions_str)
