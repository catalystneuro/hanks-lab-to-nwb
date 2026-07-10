"""Shared utilities for building session-specific FP metadata from the shared yaml."""

# AOUT channel → excitation wavelength (nm)
_AOUT_WAVELENGTH_NM = {1: 420, 2: 490, 3: 415, 4: 490}

# AIN channel → (iso_center_nm, iso_bw_nm, sig_center_nm, sig_bw_nm)
# AIN01-02: iFMC5 minicube (iso 420-435 nm, signal 470-493 nm)
# AIN03-04: iFMC4 minicube (iso 410-420 nm, signal 460-490 nm)
_AIN_TO_FILTER_SPECS = {
    1: (427.5, 15.0, 481.5, 23.0),
    2: (427.5, 15.0, 481.5, 23.0),
    3: (415.0, 10.0, 475.0, 30.0),
    4: (415.0, 10.0, 475.0, 30.0),
}

# (ain_channel, signal_type) → (aout_channel, FiberPhotometryTable row index)
# Doric lock-in wiring: AIN 1–2 share AOUT 1 (isosbestic) / AOUT 2 (signal)
#                       AIN 3–4 share AOUT 3 (isosbestic) / AOUT 4 (signal)
_AIN_TYPE_TO_AOUT_ROW = {
    # AIN  type        AOUT  row
    (1, "isosbestic"): (1, 0),
    (2, "isosbestic"): (1, 1),
    (1, "raw signal"): (2, 2),
    (2, "raw signal"): (2, 3),
    (3, "isosbestic"): (3, 4),
    (4, "isosbestic"): (3, 5),
    (3, "raw signal"): (4, 6),
    (4, "raw signal"): (4, 7),
}


def filter_optical_fibers_for_session(fp_meta: dict, ain_to_region: dict, fp_data: dict) -> None:
    """Expand the optical fiber {region} template for each region active in this session.

    Replaces the OpticalFibers list in fp_meta (in-place) with one fiber per session
    region, substituting {region} in all string fields and populating fiber_insertion
    coordinates from fp_data["implant_info"].

    Parameters
    ----------
    fp_meta :
        The Ophys.FiberPhotometry metadata dict — modified in-place.
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

    expanded = []
    for template in fp_meta.get("OpticalFibers", []):
        if "{region}" not in template.get("name", ""):
            expanded.append(template)
            continue
        for ain in sorted(ain_to_region):
            region = ain_to_region[ain]
            fiber = {k: v.replace("{region}", region) if isinstance(v, str) else v for k, v in template.items()}
            info = implant_info.get(region)
            if info:
                fiber["fiber_insertion"] = dict(
                    insertion_position_ap_in_mm=float(info["AP"]),
                    insertion_position_ml_in_mm=float(info["ML"]),
                    insertion_position_dv_in_mm=float(info["DV"]),
                    position_reference="bregma",
                    hemisphere=info["side"],
                )
            expanded.append(fiber)

    fp_meta["OpticalFibers"] = expanded

    # Expand BandOpticalFilterModels templates — one signal + one isosbestic model per region.
    # center_wavelength_in_nm and bandwidth_in_nm are injected from _AIN_TO_FILTER_SPECS.
    expanded_filter_models = []
    for template in fp_meta.get("BandOpticalFilterModels", []):
        if "{region}" not in template.get("name", ""):
            expanded_filter_models.append(template)
            continue
        is_isosbestic = "isosbestic" in template["name"]
        for ain in sorted(ain_to_region):
            region = ain_to_region[ain]
            model = {k: v.replace("{region}", region) if isinstance(v, str) else v for k, v in template.items()}
            iso_center, iso_bw, sig_center, sig_bw = _AIN_TO_FILTER_SPECS[ain]
            model["center_wavelength_in_nm"] = iso_center if is_isosbestic else sig_center
            model["bandwidth_in_nm"] = iso_bw if is_isosbestic else sig_bw
            expanded_filter_models.append(model)

    fp_meta["BandOpticalFilterModels"] = expanded_filter_models

    # Expand BandOpticalFilters instance templates — {region} replaced in all string fields,
    # including the model reference (e.g. "excitation_filter_signal_model_{region}").
    expanded_filters = []
    for template in fp_meta.get("BandOpticalFilters", []):
        if "{region}" not in template.get("name", ""):
            expanded_filters.append(template)
            continue
        for ain in sorted(ain_to_region):
            region = ain_to_region[ain]
            filt = {k: v.replace("{region}", region) if isinstance(v, str) else v for k, v in template.items()}
            expanded_filters.append(filt)

    fp_meta["BandOpticalFilters"] = expanded_filters


def patch_fp_metadata_for_session(fp_meta: dict, ain_to_region: dict) -> None:
    """Fill in session-specific fields in the shared FP metadata.

    FiberPhotometryTable rows: patches `location` and `optical_fiber`.

    FiberPhotometryResponseSeries: expands the two {region} templates from the yaml
    into one series per active region per signal type, ordered by AIN channel.
    Injects `stream_name` and `fiber_photometry_table_region` for each expanded series.

    Parameters
    ----------
    fp_meta :
        The Ophys.FiberPhotometry metadata dict — modified in-place.
    ain_to_region :
        Mapping of AIN channel numbers to brain region names,
        e.g. {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"}.
    """
    for row in fp_meta["FiberPhotometryTable"]["rows"]:
        ain_num = int(row["photodetector"].replace("PhotodetectorAIN", ""))
        region = ain_to_region[ain_num]
        row["location"] = region
        row["optical_fiber"] = f"optical_fiber_{region}"

    expanded = []
    for template in fp_meta.get("FiberPhotometryResponseSeries", []):
        if "{region}" not in template.get("name", ""):
            expanded.append(template)
            continue
        signal_type = "raw signal" if "RawSignal" in template["name"] else "isosbestic"
        for ain in sorted(ain_to_region):
            region = ain_to_region[ain]
            aout, row_idx = _AIN_TYPE_TO_AOUT_ROW[(ain, signal_type)]
            wl = _AOUT_WAVELENGTH_NM[aout]
            series = {k: v.replace("{region}", region) if isinstance(v, str) else v for k, v in template.items()}
            series["stream_name"] = f"FPConsole_Signals_Series0001_LockInAOUT0{aout}_AIN0{ain}"
            series["fiber_photometry_table_region"] = [row_idx]
            series["fiber_photometry_table_region_description"] = f"{region} {signal_type} ({wl} nm)"
            expanded.append(series)

    fp_meta["FiberPhotometryResponseSeries"] = expanded
