"""Artifact time windows from the Hanks lab fiber-photometry preprocessing workflow.

The preprocessing workflow records, per session, which spans of each region's signal are
not usable. Those spans are written here as a ``TimeIntervals`` table named
``fiber_photometry_artifacts_intervals`` so they can be read without scanning the traces
for ``NaN`` runs.

Source: ``fp_data_{sessid}.pkl`` -> ``["fp_data"]["processing_info"]``. The lab records the
same information by hand in ``Subj Info.txt`` under a ``Preprocessing Info:`` heading; where
the two disagree the pickle matches the data and is treated as authoritative.

Three window types are derived, distinguished by the ``artifact_type`` column. Each value is
documented in an attached ``MeaningsTable``, reached with
``table.get_meanings_for_column("artifact_type")``, which lists all three even in sessions where
one does not occur:

``dropout``
    From ``processing_info["dropouts"]``. Genuine loss of signal, masked in all twelve
    processed series.
``independent_range_edge``
    The gap between consecutive entries of ``processing_info["independent_ranges"]``.

    **What that key means is inferred, not documented.** The lab supplies no description of it;
    ``Subj Info.txt`` repeats the same dict and nothing else. What can be shown from the data:
    the listed spans carry values, the gap between them is ``NaN`` in exactly the ten series
    produced after filtering and baseline fitting (the two decimated ones keep their samples),
    and the raw signal steps across the boundary. The natural reading is that the spans were
    processed separately and no fit covers the join, but that has not been confirmed -- see the
    open question in embargo2026/conversion_notes.md. The stored meaning therefore claims only
    that the workflow treated the spans separately.
``pre_session_crop``
    Present when ``processing_info["ignore_sess_start"]`` is true. A deliberate crop rather
    than corrupted data, masked in the ten derived series only.

    **Unlike the other two types, the source carries no interval for this one** -- only the
    boolean flag. The window is therefore delimited from the data: it runs from the first
    sample of the time vector to the first sample that survived processing. Across every
    session shared so far that lands exactly 5 s before the first trial, which is what
    identifies the crop as anchored to the first trial, but nothing in the source states it.
    Whether the lab wants this represented as an interval at all is an open question -- see
    embargo2026/conversion_notes.md.

Every row references all twelve processed series. Most windows coincide with ``NaN`` only in
the ten derived series; the two decimated ones (``raw_iso`` / ``raw_lig``) come before
filtering and baseline fitting and carry values throughout -- but having values is not being
unaffected: at an ``independent_range_edge`` the decimated trace carries the step in the signal
that led the lab to fit the two sides separately. The window is therefore a statement about the
region's signal over that span, and applies to every series carrying it regardless of whether
that series has ``NaN`` there.

The ``NaN`` values themselves come from the preprocessing workflow and are present in the source
pickle; this interface records where they are and why, and the conversion stores every sample as
found -- verified identical, ``NaN`` positions included, with zero difference elsewhere.

**Retrieving a snippet.** ``TimeSeriesReference`` selects a range of rows, not a column, and
these series are ``(n_samples, n_regions)`` with one column per region. A reference therefore
spans every region for its time range; the row's ``location`` column names the region whose
column to take::

    row = nwbfile.intervals["fiber_photometry_artifacts_intervals"][0]
    ref = row["timeseries"].iloc[0][0]
    column = locations.index(row["location"].iloc[0])
    snippet = ref.timeseries.data[ref.idx_start : ref.idx_start + ref.count, column]
"""

import pickle
from pathlib import Path
from warnings import warn

import numpy as np
from hdmf.common import MeaningsTable
from neuroconv.basedatainterface import BaseDataInterface
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals

from hanks_lab_to_nwb.utils.build_metadata import ATLAS_REGION_NAME

TABLE_NAME = "fiber_photometry_artifacts_intervals"

TABLE_DESCRIPTION = (
    "Time windows in which the fiber photometry signal of a given region is not usable, as "
    "identified by the Hanks lab preprocessing workflow. Each row references exactly the "
    "response series the window masks."
)

# Written into the MeaningsTable, so they are read by someone holding the NWB file and not the
# lab's source files: they describe what happened to the signal, not where the annotation came
# from, and state only what can be shown from the data itself.
ARTIFACT_TYPE_DESCRIPTIONS = {
    "dropout": "Loss of fiber photometry signal in this region.",
    "independent_range_edge": (
        "Boundary between two spans of the recording that the preprocessing workflow treated "
        "separately; the processed signals have no values across it."
    ),
    "pre_session_crop": ("Start of the recording, before the first trial, discarded during preprocessing."),
}


def _normalize_windows(value) -> list[list[float]]:
    """Return ``value`` as a list of windows, tolerating both shapes the pickle uses.

    ``dropouts`` is nested in some sessions (``{'NAc': [[a, b], [c, d]]}``) and flat in others
    (``{'NAc': [a, b]}``). Reading the flat form without normalizing would yield two
    one-element windows instead of one.
    """
    if value is None:
        return []
    values = list(value)
    if not values:
        return []
    if not isinstance(values[0], (list, tuple, np.ndarray)):
        return [[float(v) for v in values]]
    return [[float(v) for v in window] for window in values]


class FiberPhotometryArtifactInterface(BaseDataInterface):
    """Write preprocessing artifact windows as a ``TimeIntervals`` table.

    Runs after the response series have been added, since each row references them.
    """

    def __init__(
        self,
        file_path: str | Path,
        ain_to_region: dict[int, str],
        signal_key_to_metadata_key: dict[str, str],
    ):
        """
        Parameters
        ----------
        file_path :
            Path to ``fp_data_{sessid}.pkl``.
        ain_to_region :
            Mapping of AIN channel numbers to region abbreviations, e.g.
            ``{1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"}``.
        signal_key_to_metadata_key :
            Mapping of ``processed_signals`` key to the ``metadata["FiberPhotometry"]`` key
            holding that series' name, e.g. ``{"dff_iso": "dff_series"}``. Series names are
            resolved from metadata rather than hard-coded so they stay in step with
            fiber_photometry.yaml.
        """
        self.ain_to_region = ain_to_region
        self.signal_key_to_metadata_key = signal_key_to_metadata_key
        super().__init__(file_path=str(file_path))

        with open(file_path, "rb") as f:
            self.fp_data = pickle.load(f)["fp_data"]

    # -- window discovery ----------------------------------------------------------------

    def _artifact_windows(self) -> list[tuple[str, float, float, str]]:
        """Return ``(region, start_time, stop_time, artifact_type)`` for every window.

        Times are Doric-clock seconds as annotated by the workflow. Callers should pass each
        window through :meth:`_snap_to_masked_extent` before use: the annotation is written to
        a tenth of a second and can overhang the masked samples at either edge.
        """
        processing_info = self.fp_data["processing_info"]
        timestamps = np.asarray(self.fp_data["time"], dtype=float)
        regions = [self.ain_to_region[ain] for ain in sorted(self.ain_to_region)]
        windows: list[tuple[str, float, float, str]] = []

        if processing_info.get("ignore_sess_start"):
            # No window is stored for this flag, so delimit it from the data: everything up to
            # the first sample that survived processing.
            stop_time = self._first_valid_time()
            if stop_time is not None:
                for region in regions:
                    windows.append((region, float(timestamps[0]), stop_time, "pre_session_crop"))

        independent_ranges = processing_info.get("independent_ranges") or {}
        for region in regions:
            spans = _normalize_windows(independent_ranges.get(region))
            # Consecutive spans leave a gap; a trailing span with no stop runs to session end.
            for earlier, later in zip(spans, spans[1:]):
                if len(earlier) > 1:
                    windows.append((region, earlier[1], later[0], "independent_range_edge"))

        dropouts = processing_info.get("dropouts") or {}
        for region in regions:
            for start_time, stop_time in _normalize_windows(dropouts.get(region)):
                windows.append((region, start_time, stop_time, "dropout"))

        windows.sort(key=lambda w: (w[1], w[0]))
        return windows

    def _first_valid_time(self) -> float | None:
        """Doric-clock time of the first sample surviving the pre-session crop."""
        timestamps = np.asarray(self.fp_data["time"], dtype=float)
        processed = self.fp_data["processed_signals"]
        for region in processed:
            for signal_key in self.signal_key_to_metadata_key:
                values = np.asarray(processed[region][signal_key], dtype=float)
                if not np.isnan(values[0]):
                    continue  # this series is not cropped; try a derived one
                valid = np.flatnonzero(~np.isnan(values))
                if valid.size:
                    return float(timestamps[valid[0]])
        return None

    def _snap_to_masked_extent(self, region: str, start_time: float, stop_time: float) -> tuple[float, float] | None:
        """Narrow an annotated window to the samples actually masked inside it.

        The workflow's annotation is written to a tenth of a second and so can overhang the
        masked samples at either edge: the ``independent_ranges`` seam annotated 2485.0-2485.1
        in session 119247, for instance, contains a valid sample at 2485.00091 before the NaN
        run begins. Snapping keeps the window to the span the processing actually affected.

        Returns ``None`` when nothing inside the annotated window is masked.
        """
        timestamps = np.asarray(self.fp_data["time"], dtype=float)
        in_window = np.flatnonzero((timestamps >= start_time) & (timestamps < stop_time))
        if not in_window.size:
            return None

        signals = self.fp_data["processed_signals"][region]
        masked_any = np.zeros(in_window.size, dtype=bool)
        for signal_key in self.signal_key_to_metadata_key:
            values = np.asarray(signals[signal_key], dtype=float)[in_window]
            masked_any |= np.isnan(values)
        if not masked_any.any():
            return None

        first = in_window[np.argmax(masked_any)]
        last = in_window[len(masked_any) - 1 - np.argmax(masked_any[::-1])]
        # Stop at the next sample so the half-open interval covers exactly the masked samples.
        stop = timestamps[last + 1] if last + 1 < timestamps.size else stop_time
        return float(timestamps[first]), float(stop)

    # -- main entry point ----------------------------------------------------------------

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, **conversion_options) -> None:
        windows = self._artifact_windows()
        if not windows:
            return

        ophys = nwbfile.processing.get("ophys")
        if ophys is None:
            raise ValueError(
                "No 'ophys' processing module on the NWBFile. "
                f"{type(self).__name__} references the fiber photometry response series and "
                "must run after the interfaces that add them."
            )

        series_by_signal_key = {}
        for signal_key, metadata_key in self.signal_key_to_metadata_key.items():
            series_name = metadata["FiberPhotometry"][metadata_key]["name"]
            if series_name in ophys.data_interfaces:
                series_by_signal_key[signal_key] = ophys[series_name]

        table = TimeIntervals(name=TABLE_NAME, description=TABLE_DESCRIPTION)
        table.add_column(name="location", description="Brain region whose signal the window masks.")
        table.add_column(name="artifact_type", description="Which part of the workflow identified the window.")

        rows = 0
        for region, annotated_start, annotated_stop, artifact_type in windows:
            snapped = self._snap_to_masked_extent(region, annotated_start, annotated_stop)
            if snapped is None:
                warn(
                    f"No masked samples inside the {artifact_type} window annotated "
                    f"{annotated_start}-{annotated_stop} s for {region}; skipping it. The "
                    "annotation and the processed signals disagree."
                )
                continue
            start_time, stop_time = snapped
            table.add_interval(
                start_time=start_time,
                stop_time=stop_time,
                location=ATLAS_REGION_NAME.get(region, region),
                artifact_type=artifact_type,
                timeseries=list(series_by_signal_key.values()),
            )
            rows += 1

        if not rows:
            return

        # artifact_type is documented once here rather than by repeating a sentence on every
        # row. A MeaningsTable is meant to list every possible value, so all three are recorded
        # even where one does not occur -- 124770 and 124949 have no dropouts, and a per-row
        # description column could not describe a type absent from the data.
        meanings = MeaningsTable(
            target=table["artifact_type"],
            description="Meaning of each artifact_type value, including values absent from this session.",
        )
        for artifact_type, meaning in ARTIFACT_TYPE_DESCRIPTIONS.items():
            meanings.add_row(value=artifact_type, meaning=meaning)
        table.add_meanings_table(meanings)

        nwbfile.add_time_intervals(table)
