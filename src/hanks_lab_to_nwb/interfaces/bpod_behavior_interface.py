"""BPod behavioral data interface for Hanks lab sess_data_{sessid}.pkl files.

Uses ndx-structured-behavior to organize behavioral data into typed tables:
  - StateTypesTable / StatesTable  — one row per state occurrence, FK to state types
  - EventTypesTable / EventsTable  — one row per animal-triggered event, FK to event types
  - ActionTypesTable / ActionsTable — one row per machine-triggered output, FK to action types
  - TrialsTable — one row per trial, DynamicTableRegion links to states/events/actions rows
  - Task (LabMetaData) — groups the type tables under nwbfile.lab_meta_data["task"]
  - TaskRecording (NWBDataInterface) — groups the data tables under nwbfile.acquisition["task_recording"]

All timestamps are Doric fiber-photometry clock seconds, converted from Bpod
trial-relative seconds via ``trial_start_ts`` in ``fp_data_{sessid}.pkl``.

Configuration that cannot be inferred from the data (excluded columns, event/action
classification, dtype overrides, descriptions) lives in bpod_behavior_columns.yaml
in the same directory.

**Abs-time naming convention**: any column whose name contains ``"time"`` and does
not start with ``"rel_"`` is treated as a Bpod trial-relative timestamp and converted
via ``+ trial_start_ts[i]`` to Doric-clock seconds. Columns starting with ``"rel_"``
hold within-trial latencies and are stored as-is. Override per-column with
``abs_time: true/false`` in the YAML.
"""

import pickle
from pathlib import Path
from warnings import warn

import numpy as np
from ndx_structured_behavior import (
    ActionsTable,
    ActionTypesTable,
    EventTypesTable,
    StatesTable,
    StateTypesTable,
    Task,
    TaskRecording,
    TrialsTable,
    add_event,
    create_events_table,
)
from neuroconv.basedatainterface import BaseDataInterface
from neuroconv.utils import DeepDict, load_dict_from_file
from pynwb import NWBFile

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


# ── event / action map normalization ──────────────────────────────────────────


def _normalize_type_value_map(raw_map: dict, name_key: str) -> dict[str, tuple[str, str]]:
    """Normalize a YAML events/actions map to ``raw_bpod_name -> (type_name, value)``.

    Raw Bpod names encode a thing and an edge in one string (``Port3In`` /
    ``Port3Out``, ``BNC1High`` / ``BNC1Low``). The mapping form splits them so the
    type table names the thing and the occurrence row's ``value`` carries the edge::

        Port3In: {event_name: Port3, value: "In"}   -> ("Port3", "In")
        Tup: "Expired"                              -> ("Tup", "Expired")

    The shorthand string form keeps the raw name as the type name.

    Parameters
    ----------
    raw_map :
        The ``events:`` or ``actions:`` block from the YAML config.
    name_key :
        ``"event_name"`` or ``"action_name"`` — the key holding the type name.
    """
    normalized: dict[str, tuple[str, str]] = {}
    for raw_name, entry in raw_map.items():
        if isinstance(entry, str):
            normalized[raw_name] = (raw_name, entry)
            continue
        if not isinstance(entry, dict):
            raise ValueError(
                f"Invalid entry for '{raw_name}': expected a value string or a mapping "
                f"with '{name_key}' and 'value', got {entry!r}."
            )
        missing = {name_key, "value"} - set(entry)
        if missing:
            raise ValueError(
                f"Invalid entry for '{raw_name}': mapping is missing {sorted(missing)}. "
                f"Expected keys '{name_key}' and 'value'."
            )
        normalized[raw_name] = (str(entry[name_key]), str(entry["value"]))
    return normalized


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
    """Merge per-column YAML config with inferred dtype into a resolved spec."""
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
    """Convert a raw pickle value to its NWB-ready type using a resolved spec."""
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
        f"Unknown dtype '{dtype}' in spec '{spec}'. "
        f"Valid values: bool, int, float, abs_time, str, "
        f"list_str, list_float, list_abs_time."
    )


class BpodBehaviorInterface(BaseDataInterface):
    """Behavioral interface for Hanks lab BPod data stored in sess_data_{sessid}.pkl.

    Populates:
    - ``nwbfile.lab_meta_data["task"]``: Task — holds StateTypesTable, EventTypesTable,
      ActionTypesTable, the type registries for all behavioral event/state/action kinds.
    - ``nwbfile.acquisition["task_recording"]``: TaskRecording — holds StatesTable,
      EventsTable, ActionsTable with one row per occurrence.
    - ``nwbfile.trials``: TrialsTable — one row per trial with DynamicTableRegion columns
      ``states``, ``events``, ``actions`` linking each trial to its rows in the data tables,
      plus all per-trial DataFrame columns not in ``excluded_columns``.

    **Table organization**:
    - ``StatesTable``: one row per state occurrence; ``state_type`` DynamicTableRegion → StateTypesTable.
    - ``EventsTable`` (core pynwb): one row per animal-triggered port contact; ``event_type``
      DynamicTableRegion → EventTypesTable; ``value`` column holds "In", "Out", or "Unknown".
    - ``ActionsTable``: one row per machine-triggered output; ``action_type`` DynamicTableRegion
      → ActionTypesTable; ``value`` column holds "On", "Off", "End", "Expired".

    **Type name vs. value**: the type tables name the physical thing (``Port1``, ``BNC1``)
    and the occurrence row's ``value`` carries the edge, so the raw Bpod names
    ``Port1In`` / ``Port1Out`` share one event type and ``BNC1High`` / ``BNC1Low`` share
    one action type. The raw Bpod name is recoverable as ``name + value``. The split is
    configured per raw name in bpod_behavior_columns.yaml.

    All timestamps are Doric fiber-photometry clock seconds, converted from Bpod
    trial-relative seconds via ``trial_start_ts`` in ``fp_data_{sessid}.pkl``.
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
        default_configuration = self.get_default_configuration()
        self._event_map = _normalize_type_value_map(default_configuration["events"], "event_name")
        self._action_map = _normalize_type_value_map(default_configuration["actions"], "action_name")
        self._states_to_skip = frozenset(default_configuration["states_to_skip"])
        self._excluded_columns = frozenset(default_configuration["excluded_columns"])
        self._column_overrides = default_configuration.get("columns", {})

        super().__init__(file_path=str(file_path), fp_data_path=str(fp_data_path))

    def get_metadata(self) -> DeepDict:
        metadata = super().get_metadata()
        metadata["Behavior"] = dict(
            Device=dict(name="bpod", manufacturer="Sanworks", description="Bpod State Machine r2"),
            StateTypesTable=dict(description="Names of the Bpod states in the task."),
            StatesTable=dict(description="Start and stop times of each Bpod state occurrence, Doric-clock seconds."),
            EventTypesTable=dict(description="Names of the animal-triggered port contact events."),
            EventsTable=dict(description="Timestamps of animal-triggered port contacts (In/Out), Doric-clock seconds."),
            ActionTypesTable=dict(description="Names of the machine-triggered output actions."),
            ActionsTable=dict(
                description="Timestamps of machine-triggered outputs (BNC TTLs, global timers, conditions), Doric-clock seconds."
            ),
            TrialsTable=dict(description="Trial start/stop times and behavioral outcomes, Doric-clock seconds."),
        )
        return metadata

    def get_metadata_schema(self) -> dict:
        """Declare the Behavior keys written by get_metadata().

        ExternalVideoInterface contributes a "Behavior" schema with
        additionalProperties=False, so these keys must be declared or the merged
        converter schema rejects them whenever a session also has video.
        """
        metadata_schema = super().get_metadata_schema()
        table_keys = (
            "StateTypesTable",
            "StatesTable",
            "EventTypesTable",
            "EventsTable",
            "ActionTypesTable",
            "ActionsTable",
            "TrialsTable",
        )
        properties = {key: dict(type="object", properties=dict(description=dict(type="string"))) for key in table_keys}
        properties["Device"] = dict(
            type="object",
            properties=dict(
                name=dict(type="string"),
                manufacturer=dict(type="string"),
                description=dict(type="string"),
            ),
        )
        metadata_schema["properties"]["Behavior"] = dict(type="object", properties=properties)
        return metadata_schema

    # ── load configuration (events, actions, excluded columns etc.)  ─────────────

    @staticmethod
    def get_default_configuration() -> dict:
        """Return the default configuration dict from bpod_behavior_columns.yaml."""
        default_configuration_path = Path(__file__).parent / "bpod_behavior_columns.yaml"
        default_configuration = load_dict_from_file(default_configuration_path)
        return default_configuration

    def register_configuration(self, config: dict) -> None:
        """Register a configuration dict to override the default YAML config.

        The config dict must have the same structure as bpod_behavior_columns.yaml.
        Under events/actions each raw Bpod name maps either to a mapping giving the
        type name and the value, or to a plain value string (type name = the raw name):
        events:
            Port1In: {"event_name": "Port1", "value": "In"}
            Port1Out: {"event_name": "Port1", "value": "Out"}
        actions:
            BNC1High: {"action_name": "BNC1", "value": "On"}
            Tup: "Expired"
        excluded_columns:
            - "column_to_exclude_1"
            - "column_to_exclude_2"
        columns:
            column_name_1:
                description: "Description of column_name_1"

        Parameters
        ----------
        config : dict
            Configuration dictionary with the same structure as bpod_behavior_columns.yaml.
            Overrides the default configuration loaded from the YAML file.
        """
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary.")
        if "events" in config:
            self._event_map = _normalize_type_value_map(config["events"], "event_name")
        if "actions" in config:
            self._action_map = _normalize_type_value_map(config["actions"], "action_name")
        self._excluded_columns = frozenset(config.get("excluded_columns", list(self._excluded_columns)))
        self._column_overrides = config.get("columns", self._column_overrides)

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
        """Resolve dtype/description for every TrialsTable column from the DataFrame."""
        specs = {}
        for col in df.columns:
            if col in self._excluded_columns:
                continue
            if df[col].isna().all():
                continue
            col_cfg = self._column_overrides.get(col, {})
            specs[col] = _resolve_col_spec(col, df[col], col_cfg)
        return specs

    # ── unmapped event detection ──────────────────────────────────────────────

    def _collect_unmapped_event_names(self, df) -> set[str]:
        """Return Bpod event names present in data but absent from both YAML maps.

        Logs a warning so they can be classified deliberately.
        """
        names: set[str] = set()
        for _, row in df.iterrows():
            names.update(row["parsed_events"]["Events"].keys())
        unmapped = names - set(self._event_map) - set(self._action_map)
        if unmapped:
            warn(
                f"Unmapped Bpod event names found in {self.source_data['file_path']}: "
                f"{', '.join(sorted(unmapped))}.  Add to bpod_behavior_columns.yaml "
                "under 'events' or 'actions' to classify them. "
                "Or call register_configuration() with a dict containing the new mappings."
            )
        return unmapped

    # ── type table builders ───────────────────────────────────────────────────

    def _build_type_tables(
        self, beh_meta: dict, df, unmapped_names: set[str]
    ) -> tuple[StateTypesTable, dict, EventTypesTable, dict, ActionTypesTable, dict]:
        """Build StateTypesTable, EventTypesTable, ActionTypesTable.

        State types are discovered from the data (only non-skipped state names).
        Event types include all YAML-defined events plus any unmapped names.
        Action types include all YAML-defined actions.

        Several raw Bpod names can share one type row — ``Port3In`` and ``Port3Out``
        both map to the ``Port3`` event type, ``BNC1High`` and ``BNC1Low`` to the
        ``BNC1`` action type — so the type names are deduplicated here, in YAML order.
        The returned index maps are keyed by *type* name, not by raw Bpod name.

        Returns
        -------
        (state_types, state_name_to_idx,
         event_types, event_name_to_idx,
         action_types, action_name_to_idx)
        """
        # State types — discover unique non-skipped state names from data
        state_types = StateTypesTable(description=beh_meta["StateTypesTable"]["description"])
        state_name_to_idx: dict[str, int] = {}
        for _, row in df.iterrows():
            for name in row["parsed_events"]["States"]:
                if name not in self._states_to_skip and name not in state_name_to_idx:
                    state_name_to_idx[name] = len(state_name_to_idx)
                    state_types.add_row(state_name=name, check_ragged=False)

        # Event types — YAML-defined + unmapped (for cross-session consistency)
        event_types = EventTypesTable(description=beh_meta["EventTypesTable"]["description"])
        event_name_to_idx: dict[str, int] = {}
        for type_name, _ in self._event_map.values():
            if type_name not in event_name_to_idx:
                event_name_to_idx[type_name] = len(event_name_to_idx)
                event_types.add_row(event_name=type_name, check_ragged=False)
        # Add any unmapped names to the event types table so they can be stored even if not classified yet
        for name in sorted(unmapped_names):  # sorted for determinism
            if name not in event_name_to_idx:
                event_name_to_idx[name] = len(event_name_to_idx)
                event_types.add_row(event_name=name, check_ragged=False)

        # Action types — YAML-defined
        action_types = ActionTypesTable(description=beh_meta["ActionTypesTable"]["description"])
        action_name_to_idx: dict[str, int] = {}
        for type_name, _ in self._action_map.values():
            if type_name not in action_name_to_idx:
                action_name_to_idx[type_name] = len(action_name_to_idx)
                action_types.add_row(action_name=type_name, check_ragged=False)

        return (state_types, state_name_to_idx, event_types, event_name_to_idx, action_types, action_name_to_idx)

    # ── data table population ─────────────────────────────────────────────────

    def _populate_data_tables(
        self,
        beh_meta: dict,
        df,
        trial_start_ts: np.ndarray,
        state_types: StateTypesTable,
        state_name_to_idx: dict,
        event_types: EventTypesTable,
        event_name_to_idx: dict,
        action_types: ActionTypesTable,
        action_name_to_idx: dict,
    ) -> tuple[StatesTable, object, ActionsTable, list, list, list]:
        """Build and populate StatesTable, EventsTable, ActionsTable in one pass.

        Returns (states_table, events_table, actions_table,
                 trial_state_indices, trial_event_indices, trial_action_indices)
        where ``trial_*_indices[i]`` is a list of row indices into the corresponding
        table that belong to trial ``i``.
        """
        states_table = StatesTable(
            description=beh_meta["StatesTable"]["description"],
            state_types_table=state_types,
        )
        events_table = create_events_table(
            event_types_table=event_types,
            description=beh_meta["EventsTable"]["description"],
            name="events",
        )
        actions_table = ActionsTable(
            description=beh_meta["ActionsTable"]["description"],
            action_types_table=action_types,
        )

        trial_state_indices: list[list[int]] = []
        trial_event_indices: list[list[int]] = []
        trial_action_indices: list[list[int]] = []
        state_row = event_row = action_row = 0

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = trial_start_ts[i]
            s_rows: list[int] = []
            e_rows: list[int] = []
            a_rows: list[int] = []

            # States.
            trial_states = [
                (float(t0 + start_rel), float(t0 + stop_rel), state_name_to_idx[name])
                for name, vals in row["parsed_events"]["States"].items()
                if name not in self._states_to_skip
                for start_rel, stop_rel in _decode_state_times(vals)
            ]
            for start_abs, stop_abs, type_idx in sorted(trial_states):
                states_table.add_row(
                    state_type=type_idx,
                    start_time=start_abs,
                    stop_time=stop_abs,
                )
                s_rows.append(state_row)
                state_row += 1

            # Events and actions (both sourced from parsed_events["Events"]).
            # The raw Bpod name resolves to a (type_name, value) pair; unmapped names
            # fall back to their raw name as the event type, with value "Unknown".
            # As with states, parsed_events["Events"] is keyed by name, so collect the
            # trial's occurrences and sort by timestamp before writing any rows.
            trial_events: list[tuple[float, int, str]] = []
            trial_actions: list[tuple[float, int, str]] = []
            for name, raw_ts in row["parsed_events"]["Events"].items():
                if name in self._event_map:
                    type_name, value = self._event_map[name]
                    target, index_map = trial_events, event_name_to_idx
                elif name in self._action_map:
                    type_name, value = self._action_map[name]
                    target, index_map = trial_actions, action_name_to_idx
                elif name in event_name_to_idx:
                    type_name, value = name, "Unknown"
                    target, index_map = trial_events, event_name_to_idx
                else:
                    continue
                for ts_rel in _to_list(raw_ts):
                    target.append((float(t0 + ts_rel), index_map[type_name], value))

            for timestamp, type_idx, value in sorted(trial_events):
                add_event(
                    events_table,
                    event_type=type_idx,
                    timestamp=timestamp,
                    value=value,
                )
                e_rows.append(event_row)
                event_row += 1

            for timestamp, type_idx, value in sorted(trial_actions):
                actions_table.add_row(
                    action_type=type_idx,
                    timestamp=timestamp,
                    value=value,
                )
                a_rows.append(action_row)
                action_row += 1

            trial_state_indices.append(s_rows)
            trial_event_indices.append(e_rows)
            trial_action_indices.append(a_rows)

        return (
            states_table,
            events_table,
            actions_table,
            trial_state_indices,
            trial_event_indices,
            trial_action_indices,
        )

    # ── main entry point ──────────────────────────────────────────────────────

    def add_to_nwbfile(self, nwbfile: NWBFile, metadata: dict, conversion_options: dict | None = None) -> None:
        df, trial_start_ts = self._load()
        beh_meta = metadata.get("Behavior", self.get_metadata()["Behavior"])

        unmapped_names = self._collect_unmapped_event_names(df)

        # Build type registries
        (
            state_types,
            state_name_to_idx,
            event_types,
            event_name_to_idx,
            action_types,
            action_name_to_idx,
        ) = self._build_type_tables(beh_meta, df, unmapped_names)

        # Build and populate data tables, tracking per-trial row indices
        (
            states_table,
            events_table,
            actions_table,
            trial_state_indices,
            trial_event_indices,
            trial_action_indices,
        ) = self._populate_data_tables(
            beh_meta,
            df,
            trial_start_ts,
            state_types,
            state_name_to_idx,
            event_types,
            event_name_to_idx,
            action_types,
            action_name_to_idx,
        )

        # Task (LabMetaData) groups the type registries
        task = Task(
            event_types=event_types,
            state_types=state_types,
            action_types=action_types,
        )
        nwbfile.add_lab_meta_data(task)

        # TaskRecording (NWBDataInterface) groups the data tables
        recording = TaskRecording(events=events_table, states=states_table, actions=actions_table)
        nwbfile.add_acquisition(recording)

        # TrialsTable with DynamicTableRegion links to states/events/actions
        trials = TrialsTable(
            description=beh_meta["TrialsTable"]["description"],
            states_table=states_table,
            events_table=events_table,
            actions_table=actions_table,
        )

        # Pre-register per-trial columns with descriptions before adding rows
        col_specs = self._build_col_specs(df)
        for name, spec in col_specs.items():
            trials.add_column(
                name=name,
                description=spec["description"],
                index=spec["dtype"] in _LIST_DTYPES,
            )

        for i, (_, row) in enumerate(df.iterrows()):
            t0 = float(trial_start_ts[i])
            t1 = float(trial_start_ts[i + 1]) if i + 1 < len(trial_start_ts) else np.nan
            extra_cols = {col: _coerce(spec, row[col], t0=t0) for col, spec in col_specs.items()}
            trials.add_row(
                start_time=t0,
                stop_time=t1,
                states=trial_state_indices[i],
                events=trial_event_indices[i],
                actions=trial_action_indices[i],
                **extra_cols,
            )

        nwbfile.trials = trials

        if "Device" in beh_meta:
            nwbfile.create_device(**beh_meta["Device"])
