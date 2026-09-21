# Hanks Lab — Conversion Notes

Two behavioral tasks are covered in this conversion, both using the same subjects,
hardware, and FP pipeline. Only the behavioral protocol and session descriptions differ.

---

## Experiment Overview

Rats are implanted with optical fibers targeting up to four striatal and prefrontal
regions and injected with AAV9-CAG-dLight3.8 (UNC Vector Core) for dopamine imaging.
Two protocols are collected per subject:

- **Bandit task (ClassicRLTasks)**: Rat chooses left or right reward port. Reward
  probabilities are fixed within a block and switch across blocks, requiring tracking
  of reward history. Behavioral events controlled by Bpod.
- **WM task (ToneCatDelayResp)**: Rat hears 1 auditory tone during a stimulus window
  and must remember the tone category to poke the correct side port after a delay.
  Behavioral events controlled by Bpod.

Dopamine signals recorded simultaneously from up to 4 brain regions via Doric FP system.

---

## Data Streams

| Stream | Format | File pattern | Interface |
|--------|--------|-------------|-----------|
| FP raw (LockIn) | Doric HDF5 `.doric` | `Session_{sessid}.doric` | `DoricFiberPhotometryInterface` |
| FP processed (dFF) | Python pickle `.pkl` | `fp_data_{sessid}.pkl` | `ProcessedFiberPhotometryInterface` |
| Behavioral data | Python pickle `.pkl` | `sess_data_{sessid}.pkl` | `BpodBehaviorInterface` (both tasks, protocol auto-detected) |
| Video | `.mp4` | `mov_{sessid}.mp4` | `ExternalVideoInterface` (follow-up PR) |

---

## Doric File Structure

```
DataAcquisition/FPConsole/Signals/Series0001/
  LockInAOUT01/AIN01  Username='Ch1_420'  shape=(26,653,687,)  — Ch1 @ 420 nm (isosbestic)
  LockInAOUT01/AIN02  Username='Ch2_420'  shape=(26,653,687,)  — Ch2 @ 420 nm
  LockInAOUT02/AIN01  Username='Ch1_490'                       — Ch1 @ 490 nm (ligand)
  LockInAOUT02/AIN02  Username='Ch2_490'                       — Ch2 @ 490 nm
  LockInAOUT03/AIN03  Username='Ch3_420'                       — Ch3 @ 415 nm (iso; username mislabeled)
  LockInAOUT03/AIN04  Username='Ch4_420'                       — Ch4 @ 415 nm
  LockInAOUT04/AIN03  Username='Ch3_490'                       — Ch3 @ 490 nm
  LockInAOUT04/AIN04  Username='Ch4_490'                       — Ch4 @ 490 nm
  DigitalIO/DIO01                                               — Bpod TTL trial sync
  DigitalIO/DIO04                                               — camera trigger
  AnalogIn/AIN01–04                                            — raw photodetector voltages
```

- LockIn time starts at ~0.083 s, dt=0.000166 s (6024.10 Hz), session ~4424 s
- DIO01 encodes trial numbers as 15-bit binary RLE; decoded by `acq_utils.parse_trial_times()`

---

## Processed FP Data (fp_data_{sessid}.pkl)

```python
{
  'fp_data': {
    'trial_start_ts': (n_trials+1,),  # Doric-clock timestamps of trial starts
    'time': (n_samples,),             # decimated timestamps (200 Hz / 5 ms)
    'dec_info': {'decimation': 30, 'initial_dt': 0.000166, 'decimated_dt': 0.00498},  # 6024.1 Hz / 30 ≈ 200.8 Hz
    'raw_signals':       {region: {wavelength_str: array}},
    'processed_signals': {region: {'raw_lig', 'raw_iso', 'filtered_lig', 'filtered_iso',
                                   'fitted_iso', 'dff_iso', 'dff_iso_baseline_fband',
                                   'lig', 'iso', ...}},
  },
  'implant_info': {region: {'side', 'AP', 'ML', 'DV', 'fiber_type'}},
  'subj_id': int,
  'sess_id': int,
}
```

---

## Behavioral Data (sess_data_{sessid}.pkl)

pandas DataFrame, one row per trial.

### Common columns (both tasks)

| Column | Type | Description |
|--------|------|-------------|
| `sessid` | int | Session ID |
| `subjid` | int | Subject ID |
| `protocol` | str | Protocol name (`ClassicRLTasks` or `ToneCatDelayResp`) |
| `sessiondate` | date | Session date |
| `starttime` | Timedelta | Time-of-day session start (Bpod) |
| `trial` | int | Trial number (1-indexed) |
| `trialtime` | Timestamp | Wall-clock time trial was logged to DB (≈ next trial start) |
| `parsed_events` | dict | `States` and `Events` in Bpod trial-relative seconds |
| `hit` | bool | Valid response made |
| `reward` | int | Reward volume (µL); 0 if unrewarded |
| `choice` | str | `'left'`, `'right'`, or `'none'` |
| `cpoke_in_time` | float | Center port in (trial-relative s) |
| `cpoke_out_time` | float | Center port out (trial-relative s) |
| `stim_start_time` | float | Stimulus onset (trial-relative s) |
| `response_cue_time` | float | Response cue onset (trial-relative s) |
| `response_time` | float | Side port poke (trial-relative s) |
| `reward_time` | float | Reward delivery (trial-relative s) |
| `RT` | float | Reaction time (s) |
| `cport_on_time` | float | Center port LED on (trial-relative s) |

### Bandit-specific columns

| Column | Type | Description |
|--------|------|-------------|
| `block_num` | int | Block number within session |
| `block_trial` | int | Trial index within current block |
| `block_prob` | str | Block reward-probability schedule for the session, e.g. `50/10` (session-level, not per-block) |
| `p_reward_left` | float | Reward probability of left port this trial |
| `p_reward_right` | float | Reward probability of right port this trial |
| `high_port` | str | Port with higher reward probability (`'left'` or `'right'`) |
| `high_side` | str | Same as high_port (alternative column name) |
| `forced_choice` | bool | Forced choice trial (only one port active) |
| `viol` | bool | Protocol violation (e.g. premature withdrawal) |
| `epoch_schedule` | str | Volatility epoch schedule for the session; `none` when there is no epoch structure |
| `epoch_label` | str | Volatility epoch label |
| `trial_length` | float | Total trial duration (s) |
| `chose_high` | bool | Animal chose the high-probability port |

### WM-specific columns

| Column | Type | Description |
|--------|------|-------------|
| `n_tones` | int | Number of tones in the sequence |
| `tone_info` | list[str] | Tone categories heard (e.g. `['high', 'low']`) |
| `relevant_tone_info` | str | The task-relevant tone category |
| `relevant_tone_port` | str | Port corresponding to relevant tone |
| `abs_tone_start_times` | float | Tone onset, trial-relative s (= rel + stim_start) |
| `abs_tone_end_times` | float | Tone offset, trial-relative s |
| `rel_tone_start_times` | float | Tone onset relative to stim_start_time |
| `rel_tone_end_times` | float | Tone offset relative to stim_start_time |
| `tone_db_offsets` | float | Per-tone dB offset from baseline |
| `stim_dur` | float | Stimulus window duration (s) |
| `cue_start_time` | float | Response cue start (trial-relative s) |
| `cue_end_time` | float | Response cue end (trial-relative s) |
| `correct_port` | str | Correct side port for this trial |
| `bail` | bool | Animal withdrew before making response |

### Timing note

All event times are **trial-relative seconds** (Bpod resets to 0 at each trial start), and the
interface shifts them onto the Doric clock via `trial_start_ts`.

Verified against the source pickles for all four sessions (2026-09-21): every column the
`abs_time` convention shifts falls 100% within its own trial's Bpod state span, and
`cport_on_time`, `response_cue_time` and `reward_time` match the start of `WaitForCenterPoke`,
`CueResponse` and `DeliverReward` exactly (`stim_start_time` is one Bpod tick after `Stimulus`
opens). Columns prefixed `rel_` are in a different frame — relative to *stimulus onset*, not trial
start — confirmed by `abs_tone_start_times == stim_start_time + rel_tone_start_times` holding
exactly; they are correctly left unshifted.

Note the lab's `abs_` prefix does not mean absolute in the source: those values are trial-relative
too, and only become absolute after conversion.

---

## Subjects

| subject_id | Sex | Strain | DOB | Weight | Species | Virus | Regions |
|------------|-----|--------|-----|--------|---------|-------|---------|
| 400 | M | Long Evans | 2024-03-19 | 530 g | Rattus norvegicus | AAV9-CAG-dLight3.8 (UNC) | PL, NAc, DMS, DLS |
| 238 | M | Long Evans | 2025-05-?? ⚠️ | 540 g | Rattus norvegicus | AAV9-CAG-dLight3.8 (UNC) | NAc, DMS, DLS, TS |

⚠️ Subject 238 DOB: lab reported `2025-05-0` — using `2025-05-01` as placeholder until confirmed.

**Experimenter**: Stevenson, Tanner

### Sessions (from Subj Info.txt)

| session_id | subject_id | Task | Trials | AIN→region mapping |
|------------|------------|------|--------|--------------------|
| 119247 | 400 | WM | 165 | 1→DLS, 2→PL, 3→DMS, 4→NAc |
| 119974 | 400 | Bandit | 304 | 1→NAc, 2→PL, 3→DLS, 4→DMS |
| 124770 | 238 | WM | 239 | 1→DMS, 2→DLS, 3→TS, 4→NAc |
| 124949 | 238 | Bandit | 323 | 1→NAc, 2→DMS, 3→TS, 4→DLS |

Full Drive folder pulled 2026-09-21 (27.2 GiB, 22 objects); all four sessions have
`.doric` + `fp_data` + `sess_data` + video locally. `Session_117242.doric` is also present but
has no matching `sess_data`/`fp_data`, so it is excluded from conversion (see Open Questions).

### Implant coordinates (from fp_data_*.pkl → implant_info, mm re bregma)

**Subject 400**: PL right (+3.0, -0.6, -3.0) · NAc left (+1.6, +1.6, -7.2) ·
DMS right (+1.1, -2.1, -3.6) · DLS left (+0.6, +3.8, -3.8)

**Subject 238**: NAc right (+1.6, -1.6, -7.0) · DMS left (+1.1, +2.0, -3.6) ·
DLS right (+0.4, -3.8, -3.8) · TS left (-1.0, +3.8, -3.8)

---

## Fiber Photometry Hardware

- **System**: Doric Fiber Photometry Console, 4-channel LED driver
  - Channels 1–2: 2× iFMC5 minicube (E 470-493 nm / IE 420-435 nm / F 500-550 nm)
  - Channels 3–4: 2× iFMC4 minicube (E 460-490 nm / IE 410-420 nm / F 500-550 nm)
- **Excitation sources**:
  - Isosbestic: Doric Connecterized 415 nm LED, FWHM 13 nm
    - AOUT01 paired with 420-435 nm filter → drives AIN01-02
    - AOUT03 paired with 410-420 nm filter → drives AIN03-04 (labeled "Ch3_420" in software — display only)
  - Signal: Doric Connecterized 490 nm LED, FWHM 26 nm
- **Optical fibers**: RWD R-FOC-BL400C-50NA, flat 400 µm core, NA 0.5, 1.25 mm ceramic ferrule
- **Photodetector**: Doric iFMC integrated Si photodiode, gain 7.6 V/nW, sensitivity 350-1000 nm
  - 960 nm = bare Si chip peak; detected wavelength through emission filter is ~525 nm
- **Emission filter**: 500-550 nm bandpass (all 4 channels)
- **Excitation filters**: ch 1-2 signal 470-493 nm / iso 420-435 nm; ch 3-4 signal 460-490 nm / iso 410-420 nm
- **Indicator**: AAV9-CAG-dLight3.8, UNC Vector Core; excitation ~490 nm, isosbestic ~420 nm, emission ~530 nm
- **Atlas**: Paxinos & Watson rat brain, 7th edition, bregma reference

---

## Synchronization

### Clocks
- **Doric**: hardware timer, reference clock for NWB. First sample at ~0.083 s.
- **Bpod**: resets to 0 at each trial start (trial-relative); drives DIO01 TTL.
- **Wall clock**: Doric file `Created` attribute (used as `session_start_time`).

### Mechanism
Bpod drives the DIO01 line on the Doric system, encoding each trial number as a
15-bit binary RLE pulse train. The Doric ADC samples DIO01 at the same 6024 Hz clock
as the FP channels. `acq_utils.parse_trial_times()` decodes trial boundaries from this
sampled trace, returning `trial_start_ts` — timestamps already in the Doric clock.
No cross-system synchronization is needed.

### NWB alignment

```
session_start_time = Doric file Created attribute (America/Los_Angeles tz)

FP NWB timestamp   = doric_time          (no offset; Doric IS the reference clock)
Behavioral event   = trial_start_ts[trial_i] + bpod_trial_relative_time
```

Pre-trial baseline (~12–15 s) has positive timestamps; first trial at `trial_start_ts[0]`.

---

## NWB Design

### FP data → ndx-fiber-photometry
- `FiberPhotometryTable`: one row per (region × wavelength) channel
- `FiberPhotometryResponseSeries` in `acquisition`: raw LockIn signals (from .doric)
- `FiberPhotometryResponseSeries` in `processing["ophys"]`: dFF signals (from pkl) → `FiberPhotometryResponseSeriesDFF`
- `OpticalFiber` with `FiberInsertion` per implanted region (AP/ML/DV from pkl)

### Behavior → ndx-structured-behavior (`BpodBehaviorInterface`)

Uses ndx-structured-behavior 0.2.0 (installed from `../ndx-structured-behavior` editable,
via `[tool.uv.sources]` in pyproject.toml). The 0.2.0 release removes the `EventsTable`
name collision with pynwb ≥ 4.0 by re-using the core namespace type.

**NWB structure:**
- `nwbfile.lab_meta_data["task"]` (`Task`): type registries
  - `StateTypesTable`: unique state names discovered from data
  - `EventTypesTable`: event names from `bpod_behavior_columns.yaml events:` + unmapped
  - `ActionTypesTable`: action names from `bpod_behavior_columns.yaml actions:`
- `nwbfile.acquisition["task_recording"]` (`TaskRecording`): occurrence tables
  - `StatesTable`: one row per state occurrence; `state_type` DynamicTableRegion → `StateTypesTable`
  - `EventsTable` (core pynwb): one row per animal-triggered event; `event_type` DynamicTableRegion
    → `EventTypesTable`; `value` = "In"/"Out"/"Unknown"
  - `ActionsTable`: one row per machine-triggered output; `action_type` DynamicTableRegion
    → `ActionTypesTable`; `value` = "On"/"Off"/"End"/"Expired"
- `nwbfile.trials` (`TrialsTable`): one row per trial
  - `states`, `events`, `actions` DynamicTableRegion columns link each trial to its rows
    in the data tables
  - All per-trial DataFrame columns added automatically (not in `excluded_columns`)
  - All event times converted: Bpod trial-relative → Doric-clock absolute
    via `trial_start_ts` from `fp_data_{sessid}.pkl`

### Video → external reference
- `ImageSeries(external_file=[...])` pointing to `mov_{sessid}.mp4`, stored as the bare file name
  so the path resolves when the mp4 is uploaded beside the `.nwb` (NWB requires `external_file` to
  be relative to the NWB file). Frame timestamps come from the companion `mov_{sessid}.doric`
  behavior-camera clock, verified equal for all four sessions.

---

## Open Questions


### 1. Does `n_tones` ever exceed 1 in `ToneCatDelayResp`?  *(open, 2026-09-21)*

**Context.** The trials table stores six per-tone columns as *ragged* (list-valued) columns:
`tone_info`, `abs_tone_start_times`, `abs_tone_end_times`, `rel_tone_start_times`,
`rel_tone_end_times`, `tone_db_offsets`.

Checked against **both** WM sessions (2026-09-21, after pulling the full Drive folder):

| session | subject | trials | `n_tones` |
|---|---|---|---|
| 119247 | 400 | 165 | 1 on every trial |
| 124770 | 238 | 239 | 1 on every trial |

404 WM trials, `n_tones == 1` throughout, both `ToneCatDelayResp` **stage 7**. `tone_info` is a
1-element list and the five time/offset columns are plain scalars in both. This is a property of
the data, not a truncation bug in the interface (all trials round-trip element-for-element).

In the raw DataFrame only `tone_info` is genuinely a list; the five time/offset columns are
plain scalars and are promoted to 1-element lists by the explicit `dtype: list_*` overrides in
`src/hanks_lab_to_nwb/interfaces/bpod_behavior_columns.yaml`.

**Decision.** Keep the ragged columns. Making the indexing data-driven (ragged only when
`max(n_tones) > 1`) would give the same column two different types across sessions in one
dandiset and break cross-session queries.

**To confirm with the lab:**
- Does any `ToneCatDelayResp` session or training stage present more than one tone per trial?
  The plural column names, the `n_tones` column, and `relevant_tone_info` / `relevant_tone_port`
  (which only make sense when selecting one tone out of several) all suggest yes, but neither
  shared WM session exercises it — both are stage 7, which appears to be single-tone by design.
- If multi-tone stages exist, can they share one such session so that path is actually exercised?
- Is stage 7 single-tone *by definition*, with `n_tones > 1` only at other stages? If so the
  ragged columns are future-proofing for data we may never receive, which is still the right
  call for schema stability but should be stated as such.

### 2. `bail_tone_time` is present in 124770 but absent in 119247  *(open, 2026-09-21)*

Both sessions are `ToneCatDelayResp` stage 7 with an identical Bpod state vocabulary (no state
name differs between them), so this is a difference in the **lab's post-processing version**,
not in the task. The column appears on exactly the 107 bail trials of 124770 and is derived,
not independently measured: `bail_tone_time == cpoke_out_time + 0.3 s` on all 107 rows.

Session 119247 has 15 bail trials and no such column.

**To confirm with the lab:** is the 0.3 s bail-tone delay fixed across sessions, and was 119247
processed with an older script? If the delay is a constant of the protocol the column is pure
redundancy and could be excluded; we keep it for now with a description saying how it is derived.

### 3. Subject 238 date of birth  *(open)*

Lab reported `"2025-05-0"`; currently assumed `2025-05-01` in `convert_session.py`.

### Resolved

- **Processed signal descriptions** (confirmed by lab 2026-08-25) — all 12 pkl key
  descriptions confirmed. `fiber_photometry.yaml` updated to match exactly.

- **Timestamps** (confirmed by lab 2026-08-25) — `fp_data["fp_data"]["time"]` (Doric
  clock decimated 30×, ~200 Hz) is correct for all 12 processed series; no offset needed.

- **Series inclusion** (confirmed by lab 2026-08-25) — all 12 processed series should
  be included in NWB.

### Design decisions settled during conversion


- **Tone time bases.** `abs_tone_start_times == stim_start_time + rel_tone_start_times` holds
  exactly (max abs deviation 4.5e-13 s over session 119247). `rel_*` is relative to stimulus
  onset, not to center-poke onset.
- **Empty `abs_*` tone lists.** 9 / 165 trials in session 119247 have `NaN` absolute tone times
  in the raw data and therefore empty lists in NWB: 7 trials the rat never started, plus
  2 bail trials (73, 158) where the rat withdrew from the center port before tone onset.
  The `rel_*` times, `tone_info` and `tone_db_offsets` are still populated on all 165 trials
  because Bpod had already generated the stimulus.
- **Event/action type names carry the thing, `value` carries the edge.**  Bpod's
  `Port3In` / `Port3Out` collapse to one `Port3` event type with `value` `In` / `Out`;
  `BNC1High` / `BNC1Low` collapse to one `BNC1` action type with `On` / `Off`;
  `GlobalTimerN_End` becomes `GlobalTimerN` + `End`.  This matches the Pagan Lab
  reference file, whose `EventTypesTable` is just `C`, `L`, `R`.  Event types went
  6 → 3 rows and action types 7 → 6, with zero information loss: every raw Bpod name
  is recoverable as `name + value`, verified by reconstructing all 13 raw names and
  their exact counts from the NWB file for session 119247.
  Configured per raw name in `bpod_behavior_columns.yaml`; the interface accepts both
  `{event_name: Port3, value: "In"}` and the older `Tup: "Expired"` shorthand.
- **Cross-session trials-schema audit (all 4 sessions, 2026-09-21).** `cue_start_time`,
  `cue_end_time` and `forced_hit` are dropped from the trials table by the `isna().all()` guard
  in `_build_col_specs`. Confirmed safe: they are all-NaN in *both* WM sessions and absent
  entirely from both bandit sessions, so no session silently gains a column the others lack.
  The only genuinely inconsistent column across same-task sessions is `bail_tone_time`
  (see open question 2). The two bandit sessions have identical column status throughout.
- **Fiber photometry timing stays as `rate` + `starting_time` where NeuroConv chooses it**
  (decided 2026-09-21). NeuroConv picks per file: the `.doric` clock for 124770/124949 is
  perfectly regular (dt std 5e-16 s) so those get `rate`; 119247/119974 jitter (5.5e-9 s) and get
  explicit timestamps. All 12 processed series use `rate` in every session. Forcing
  `always_write_timestamps=True` (a conversion option on both FP interfaces) was considered and
  rejected: it would add 1.12 GB across the four files (+35% on 124770/124949), it contradicts the
  NWB practice of preferring rate for regularly sampled data, and most of the cost is 12 identical
  copies of one time vector per session. Both forms reconstruct the source clock to <=1e-9 s and
  both are covered by the validation harness. Consumers should use `TimeSeries.get_timestamps()`,
  which returns the reconstructed vector for rate-based series, rather than reading `.timestamps`.
- **`session_start_time` has no fallback, by design** (decided 2026-09-21). It is read from the
  `.doric` `Created` attribute, which is the zero point of the Doric clock that every timestamp in
  the file is measured against (`trial_start_ts` in `fp_data` is in Doric-clock seconds). The old
  fallback to the Bpod session header (`sessiondate + starttime`) was removed: the Doric rig starts
  recording before Bpod does — +12 s (119247), +14 s (119974), +23 s (124770), +26 s (124949) — so a
  Bpod-derived start time lands after the file's true t=0 and misattributes every timestamp by a
  per-session amount with no constant correction. `session_to_nwb` now raises instead. Verified
  unreachable for this dataset: all four convertible sessions have a `.doric` with a valid `Created`
  attribute, and no session has `sess_data` without a `.doric` (117242 is the reverse case).
- **Fiber-photometry dropouts are not written as metadata — the data already carries them**
  (decided 2026-09-21). `fp_data["fp_data"]["processing_info"]["dropouts"]` lists per-region spans
  where the signal dropped, present in two of the four sessions:

  | Session | Region | Window | Samples NaN |
  |---|---|---|---|
  | 119247 | NAc | 2499.7 – 2500.3 s | 121 / 121 |
  | 119247 | NAc | 3067.1 – 3067.5 s | 80 / 80 |
  | 119974 | NAc | 2202.1 – 2202.3 s | 40 / 40 |
  | 119974 | DMS | 3630.4 – 3630.6 s | 40 / 40 |

  Those samples are already `NaN` in the source pickle, and the `NaN`s round-trip into the converted
  files: in both, every window is fully NaN on its own region's channel of
  `FiberPhotometryResponseSeriesDFF`, with 0 NaN on the three other channels at the same times.
  A downstream user reading that region's dF/F sees NaN and skips it, so the data self-documents
  and the windows are recoverable from it directly. We therefore do **not** duplicate the dropout
  dict into the NWB file.

  Caveat worth knowing: dropout NaNs are not the only NaNs. Per-channel totals in 119247 are
  1496 / 1535 / 1496 / 1716 of 888,457 samples, mostly filter edge effects near the session start;
  NAc's extra ~200 are the dropouts. So scanning for NaN finds the dropouts but does not by itself
  distinguish them from filter edges.

  Note this is independent of the timing representation. All processed series use `rate` in every
  session; only the raw lock-in series of 119247/119974 use explicit timestamps (see the timing
  entry above). The NaN lives in the data array, not in the clock.
- **`GenerateTrialBit1–15` states are dropped** — they encode the trial number as a 15-bit TTL
  word for Doric synchronization, not a behavioral state.

---

## Tutorials

- `tutorials/bpod_demo.ipynb` — Bpod behavior walkthrough for session 119247, structured after the
  Pagan Lab `arc_behavior_example_notebook.ipynb`.
- `tutorials/doric_fp_demo.ipynb`, `tutorials/processed_fp_demo.ipynb` — fiber photometry.

All tutorials read real conversion output from `nwb_output/`, never synthesized NWBFiles.

---

## Status

- [x] Phase 1: Experiment discovery
- [x] Phase 2: Data inspection
- [x] Phase 3: Metadata
- [x] Phase 4: Synchronization analysis
- [x] Phase 5: Code generation (FP raw + BPod behavior)
- [x] Phase 6: Testing & validation — 224 source checks across 4 sessions, 0 failures; NWB Inspector 0 messages on all four
- [ ] Phase 7: DANDI upload
