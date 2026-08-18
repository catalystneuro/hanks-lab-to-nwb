"""BPod behavioral data interface for Hanks lab sess_data_{sessid}.pkl files.

Uses only core pynwb types to avoid the ndx-structured-behavior / pynwb >= 4.0
namespace collision (pynwb 4.0 added EventsTable to the core namespace, which
conflicts with ndx-structured-behavior's own EventsTable definition and breaks TaskRecording's
type check).

# TODO: Once ndx-structured-behavior fixes the EventsTable name collision
# (e.g. by making ndx-structured-behavior's EventsTable subclass pynwb.event.EventsTable),
# consider switching back to the structured-behavior framework for richer
# semantics:
#   - StateTypesTable / StatesTable with DynamicTableRegion FK to state types
#   - EventTypesTable / EventsTable with DynamicTableRegion FK to event types
#   - TrialsTable with DynamicTableRegion FKs linking trials to state/event rows
#   - Task (LabMetaData) grouping the type registries
#   - TaskRecording (NWBDataInterface) grouping the data tables

All trial columns are auto-discovered from the DataFrame. Configuration that
cannot be inferred from the data (excluded columns, event/action capture rules,
dtype overrides, optional descriptions) lives in bpod_behavior_columns.yaml in
the same directory.

Bpod trial-relative → Doric-clock conversion is detected by column name:
any column whose name contains the substring "time" and does not start with
"rel_" is treated as a Bpod trial-relative timestamp and converted via
``+ trial_start_ts[i]``.  Columns starting with "rel_" hold within-trial
latencies that are already relative to a stimulus event and must not be
shifted.  Use ``abs_time: true/false`` in the YAML ``columns:`` section to
override this convention for a specific column.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
import yaml
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import DeepDict
from pynwb import NWBFile
from pynwb.epoch import TimeIntervals
from pynwb.event import EventsTable

_log = logging.getLogger(__name__)

# ── load configuration ────────────────────────────────────────────────────────

_CFG_PATH = Path(__file__).parent / "bpod_behavior_columns.yaml"
with _CFG_PATH.open() as _f:
    _CFG: dict = yaml.safe_load(_f)

_STATES_TO_SKIP: frozenset[str] = frozenset(_CFG["states_to_skip"])
_EVENT_VALUE_MAP: dict[str, str] = _CFG["events"]
_ACTION_VALUE_MAP: dict[str, str] = _CFG["actions"]
_EXCLUDED_COLS: frozenset[str] = frozenset(_CFG["excluded_columns"])
_COL_OVERRIDES: dict[str, dict] = _CFG.get("columns", {})

_LIST_DTYPES: frozenset[str] = frozenset({"list_str", "list_float", "list_abs_time"})


# ── abs_time detection ────────────────────────────────────────────────────────


def _is_abs_time_col(col: str) -> bool:
    """Return True if col holds a Bpod trial-relative time needing Doric-clock conversion.

    Convention: name contains "time" AND does not start with "rel_".
    - Columns starting with rel_ are within-trial latencies (e.g. rel_tone_start_times
      is relative to stimulus onset) — already in the right units, no shift needed.
    - All other *time* columns are Bpod trial-relative and require + trial_start_ts[i].

    Override per-column with abs_time: true/false in bpod_behavior_columns.yaml.
    """
    return "time" in col and not col.startswith("rel_")


# ── type inference ────────────────────────────────────────────────────────────


def _infer_col_dtype(series, abs_time: bool = False) -> str:
    """Infer the NWB storage dtype from a pandas Series.

    Checks the first non-null value since object-dtype columns may hold bools,
    ints, lists, or strings depending on content.
    """
    non_null = series.dropna()
    if non_null.empty:
        return "str"

    sample = non_null.iloc[0]

    # List → ragged. Check element type to pick list_float vs list_str.
    if isinstance(sample, list):
        if sample and isinstance(sample[0], (bool, np.bool_)):
            return "list_str"  # bool list → store as strings to avoid ambiguity
        if sample and isinstance(sample[0], (int, float, np.integer, np.floating)):
            return "list_abs_time" if abs_time else "list_float"
        return "list_str"

    # bool — must precede int check since bool subclasses int in Python
    if isinstance(sample, (bool, np.bool_)) or series.dtype == bool:
        return "bool"

    # int
    if np.issubdtype(series.dtype, np.integer) or isinstance(sample, (int, np.integer)):
        return "int"

    # float
    if np.issubdtype(series.dtype, np.floating) or isinstance(sample, (float, np.floating)):
        return "abs_time" if abs_time else "float"

    return "str"


def _resolve_col_spec(col: str, series, col_cfg: dict) -> dict:
    """Merge per-column YAML config with inferred dtype into a resolved spec.

    abs_time is derived from the column name via _is_abs_time_col; the YAML
    ``abs_time`` key overrides the name-based inference when explicitly set.
    """
    abs_time = col_cfg.get("abs_time", _is_abs_time_col(col))
    explicit_dtype = col_cfg.get("dtype")
    dtype = explicit_dtype if explicit_dtype else _infer_col_dtype(series, abs_time=abs_time)
    return {
        "dtype": dtype,
        "none_value": col_cfg.get("none_value"),
        "description": col_cfg.get("description", "no description"),
    }


# ── helpers ───────────────────────────────────────────────────────────────────


def _decode_state_times(vals: list) -> list[tuple[float, float]]:
    """Parse Bpod state list into (start, stop) pairs.

    Bpod stores multi-occurrence state times as MATLAB column-major flattening
    of an Nx2 matrix: [start1, start2, ..., stop1, stop2, ...].
    Single occurrence: [start, stop].  Absent state: [None, None].
    """
    if not vals or vals[0] is None:
        return []
    n = len(vals) // 2
    return [(float(s), float(e)) for s, e in zip(vals[:n], vals[n:]) if s is not None and e is not None]


def _to_list(val) -> list[float]:
    """Return event timestamps as a flat list of floats."""
    if val is None:
        return []
    if isinstance(val, (list, np.ndarray)):
        return [float(v) for v in val if v is not None]
    return [float(val)]


def _safe_float(val) -> float:
    if val is None:
        return np.nan
    try:
        return float(val)
    except (TypeError, ValueError):
        return np.nan


def _coerce(spec: dict, v, t0: float = 0.0):
    """Convert a raw pickle value to its NWB-ready type using a resolved spec.

    List dtypes (list_str, list_float, list_abs_time) return Python lists and
    require the trial column to be registered with index=True.
    None or missing values return empty lists for list dtypes.
    """
    dtype = spec["dtype"]
    none_value = spec.get("none_value")

    if dtype == "bool":
        return bool(v) if v is not None else False

    if dtype == "int":
        nv = int(none_value) if none_value is not None else 0
        if v is None:
            return nv
        try:
            f = float(v)
            return nv if np.isnan(f) else int(f)
        except (TypeError, ValueError):
            return nv

    if dtype == "float":
        return _safe_float(v)

    if dtype == "abs_time":
        f = _safe_float(v)
        return float(t0 + f) if not np.isnan(f) else np.nan

    if dtype == "str":
        nv = str(none_value) if none_value is not None else "none"
        return str(v) if v is not None else nv

    if dtype == "list_str":
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]

    if dtype == "list_float":
        if v is None:
            return []
        if isinstance(v, (list, np.ndarray)):
            return [_safe_float(x) for x in v]
        return [_safe_float(v)]

    if dtype == "list_abs_time":
        if v is None:
            return []
        if isinstance(v, (list, np.ndarray)):
            return [float(t0 + _safe_float(x)) for x in v]
        f = _safe_float(v)
        return [float(t0 + f)] if not np.isnan(f) else []

    raise ValueError(
        f"Unknown dtype '{dtype}' in {_CFG_PATH.name}. "
        f"Valid values: bool, int, float, abs_time, str, "
        f"list_str, list_float, list_abs_time."
    )


class BpodBehaviorInterface(BaseDataInterface):
    """Behavioral interface for Hanks lab BPod data stored in sess_data_{sessid}.pkl.

    Populates:
    - ``nwbfile.intervals["bpod_states"]``: TimeIntervals — one row per state
      occurrence, columns start_time, stop_time, state_name.
    - ``nwbfile.acquisition["bpod_events"]``: pynwb.event.EventsTable — one row
      per animal-triggered port contact (Port1In/Out, Port2In/Out, Port3In/Out),
      columns timestamp, annotation, value. Also holds any Bpod event name not
      listed under ``events:`` or ``actions:`` in bpod_behavior_columns.yaml
      (value="Unknown", a warning is logged naming them — see that file for
      where to classify and describe them).
    - ``nwbfile.acquisition["bpod_actions"]``: pynwb.event.EventsTable — one row
      per machine-triggered output (BNC TTLs, global timers, conditions),
      columns timestamp, annotation, value.
    - ``nwbfile.trials``: TimeIntervals — one row per trial. All DataFrame columns
      not in ``excluded_columns`` are added automatically; type is inferred from
      the pandas dtype and first non-null value.

    All timestamps are Doric fiber-photometry clock seconds, converted from Bpod
    trial-relative seconds via ``trial_start_ts`` in ``fp_data_{sessid}.pkl``.

    **Abs-time naming convention**: any column whose name contains ``"time"``
    and does not start with ``"rel_"`` is treated as a Bpod trial-relative
    timestamp and converted via ``+ trial_start_ts[i]`` to Doric-clock seconds.
    Columns starting with ``"rel_"`` are within-trial latencies and are stored
    as-is.  Override per-column with ``abs_time: true/false`` in the YAML.

    Configuration lives in ``bpod_behavior_columns.yaml`` (same directory).
    YAML entries are needed only for:
    - ``dtype`` override for columns whose type varies across sessions
    - ``none_value`` for non-default None fills
    - ``description`` (defaults to "no description" if absent)
    - ``abs_time: true/false`` to override the name-based abs_time detection
    """

    def __init__(self, file_path: str | Path, fp_data_path: str | Path):
        """
        Parameters
        ----------
        file_path :
            Path to ``sess_data_{sessid}.pkl`` (pandas DataFrame, one row per trial).
        fp_data_path :
            Path to ``fp_data_{sessid}.pkl``. ``trial_start_ts`` converts Bpod
            trial-relative times to Doric-clock absolute seconds.
        """
        super().__init__(file_path=str(file_path), fp_data_path=str(fp_data_path))

    def get_metadata(self) -> DeepDict:
        metadata = super().get_metadata()
        metadata["Behavior"] = dict(
            Device=dict(name="bpod", manufacturer="Sanworks", description="Bpod State Machine r2"),
            BpodStates=dict(description="Start and stop times of each Bpod state occurrence, Doric-clock seconds."),
            BpodEvents=dict(description="Timestamps of animal-triggered port contacts (In/Out), Doric-clock seconds."),
            BpodActions=dict(
                description="Timestamps of machine-triggered outputs (BNC TTLs, global timers, conditions), Doric-clock seconds."
            ),
            TrialsTable=dict(description="Trial start/stop times and behavioral outcomes, Doric-clock seconds."),
        )
        return metadata

    # ── data loading ──────────────────────────────────────────────────────────

    def _load(self):
        with open(self.source_data["file_path"], "rb") as f:
            df = pickle.load(f)
        with open(self.source_data["fp_data_path"], "rb") as f:
            fp = pickle.load(f)
        trial_start_ts = np.asarray(fp["fp_data"]["trial_start_ts"], dtype=float)
        assert len(trial_start_ts) >= len(
            df
        ), f"trial_start_ts ({len(trial_start_ts)}) shorter than DataFrame ({len(df)} trials)"
        return df, trial_start_ts

    # ── column spec resolution ────────────────────────────────────────────────

    def _build_col_specs(self, df) -> dict[str, dict]:
        """Resolve dtype/description for every trials-table column.

        Returns an ordered dict of {col_name: resolved_spec} for all DataFrame
        columns that should appear in the trials table (i.e. not excluded and
        not all-NaN).
        """
        specs = {}
        for col in df.columns:
            if col in _EXCLUDED_COLS:
                continue
            if df[col].isna().all():
                continue
            col_cfg = _COL_OVERRIDES.get(col, {})
            specs[col] = _resolve_col_spec(col, df[col], col_cfg)
        return specs

    # ── table builders ────────────────────────────────────────────────────────

    def _build_states_table(self, beh_meta: dict, df, trial_start_ts: np.ndarray) -> TimeIntervals:
        states_table = TimeIntervals(
            name="bpod_states",
            description=beh_meta["BpodStates"]["description"],
        )
        states_table.add_column("state_name", "Name of the Bpod state.")

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = trial_start_ts[i]
            for name, vals in row["parsed_events"]["States"].items():
                if name in _STATES_TO_SKIP:
                    continue
                for start_rel, stop_rel in _decode_state_times(vals):
                    states_table.add_row(
                        start_time=float(t0 + start_rel),
                        stop_time=float(t0 + stop_rel),
                        state_name=name,
                    )

        return states_table

    def _collect_unmapped_event_names(self, df) -> set[str]:
        """Return Bpod event names present in the data but absent from both
        ``events:`` and ``actions:`` in bpod_behavior_columns.yaml.

        Logs a warning naming them so they can be classified deliberately
        instead of silently disappearing from the NWB file.
        """
        names: set[str] = set()
        for _, row in df.iterrows():
            names.update(row["parsed_events"]["Events"].keys())
        unmapped = names - set(_EVENT_VALUE_MAP) - set(_ACTION_VALUE_MAP)
        if unmapped:
            _log.warning(
                "Bpod event name(s) not listed under `events:` or `actions:` in "
                "%s: %s. They will be written to nwbfile.acquisition['bpod_events'] "
                "with value='Unknown' and no description. To classify them properly, "
                "add each name under `events:` (animal-triggered) or `actions:` "
                "(machine-triggered) in that file, with its value string (e.g. In/Out/On/Off).",
                _CFG_PATH.name,
                sorted(unmapped),
            )
        return unmapped

    def _build_events_table(
        self, beh_meta: dict, df, trial_start_ts: np.ndarray, unmapped_names: set[str]
    ) -> EventsTable:
        events_table = EventsTable(
            name="bpod_events",
            description=beh_meta["BpodEvents"]["description"],
        )
        events_table.add_column(
            name="value",
            description="Value of the event (e.g. In, Out, On, Off, Expired, End, Unknown).",
        )

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = trial_start_ts[i]
            for name, raw_ts in row["parsed_events"]["Events"].items():
                if name in _EVENT_VALUE_MAP:
                    value = _EVENT_VALUE_MAP[name]
                elif name in unmapped_names:
                    value = "Unknown"
                else:
                    continue
                for ts_rel in _to_list(raw_ts):
                    events_table.add_event(
                        timestamp=float(t0 + ts_rel),
                        annotation=name,
                        value=value,
                    )

        return events_table

    def _build_actions_table(self, beh_meta: dict, df, trial_start_ts: np.ndarray) -> EventsTable:
        actions_table = EventsTable(
            name="bpod_actions",
            description=beh_meta["BpodActions"]["description"],
        )
        actions_table.add_column(
            name="value",
            description="Value of the action (e.g. On, Off, End, Expired).",
        )

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = trial_start_ts[i]
            for name, raw_ts in row["parsed_events"]["Events"].items():
                if name not in _ACTION_VALUE_MAP:
                    continue
                for ts_rel in _to_list(raw_ts):
                    actions_table.add_event(
                        timestamp=float(t0 + ts_rel),
                        annotation=name,
                        value=_ACTION_VALUE_MAP[name],
                    )

        return actions_table

    # ── trials table ──────────────────────────────────────────────────────────

    def _register_trial_columns(self, nwbfile: NWBFile, col_specs: dict) -> None:
        for name, spec in col_specs.items():
            nwbfile.add_trial_column(
                name,
                spec["description"],
                index=spec["dtype"] in _LIST_DTYPES,
            )

    def _build_trial_row(self, i: int, row, trial_start_ts: np.ndarray, col_specs: dict) -> dict:
        t0 = float(trial_start_ts[i])
        return {col: _coerce(spec, row[col], t0=t0) for col, spec in col_specs.items()}

    # ── main entry point ──────────────────────────────────────────────────────

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, conversion_options: dict | None = None) -> None:
        df, trial_start_ts = self._load()
        beh_meta = metadata.get("Behavior", self.get_metadata()["Behavior"])

        unmapped_names = self._collect_unmapped_event_names(df)

        nwbfile.add_time_intervals(self._build_states_table(beh_meta, df, trial_start_ts))
        nwbfile.add_acquisition(self._build_events_table(beh_meta, df, trial_start_ts, unmapped_names))
        nwbfile.add_acquisition(self._build_actions_table(beh_meta, df, trial_start_ts))

        col_specs = self._build_col_specs(df)
        self._register_trial_columns(nwbfile, col_specs)

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = float(trial_start_ts[i])
            t1 = float(trial_start_ts[i + 1]) if i + 1 < len(trial_start_ts) else t0
            nwbfile.add_trial(
                start_time=t0,
                stop_time=t1,
                **self._build_trial_row(i, row, trial_start_ts, col_specs),
            )

        if "Device" in beh_meta:
            nwbfile.create_device(**beh_meta["Device"])
