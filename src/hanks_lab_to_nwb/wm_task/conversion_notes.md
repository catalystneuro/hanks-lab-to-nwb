# WM Task (ToneCatDelayResp) — Conversion Notes

## Experiment Overview

Rats hear 1–2 auditory tones during a stimulus window and must remember the
relevant tone category to poke the correct side port after a delay.
Behavioral events are controlled by Bpod. Dopamine is recorded simultaneously
from up to 4 brain regions with dLight 3.8 via Doric fiber photometry.

---

## Data Streams

| Stream | Format | File pattern | Interface |
|--------|--------|-------------|-----------|
| FP raw (LockIn) | Doric HDF5 `.doric` | `Session_{sessid}.doric` | `DoricFiberPhotometryInterface` |
| FP processed (dFF) | Python pickle `.pkl` | `fp_data_{sessid}.pkl` | `FPProcessedInterface` |
| Behavioral data | Python pickle `.pkl` | `sess_data_{sessid}.pkl` | `WMBehaviorInterface` |
| Video | `.mp4` | `mov_{sessid}.mp4` | `ExternalVideoInterface` |

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
  DigitalIO/DIO04                                               — unknown (TBD)
  AnalogIn/AIN01–04                                            — raw photodetector voltages
```

- LockIn time starts at ~0.083 s, dt=0.000166 s (~6016 Hz), session ~4424 s
- DIO01 encodes trial numbers as 15-bit binary RLE; decoded by `acq_utils.parse_trial_times()`

---

## Processed FP Data (fp_data_{sessid}.pkl)

```python
{
  'fp_data': {
    'trial_start_ts': (166,),  # Doric-clock timestamps of trial starts
    'time': (888457,),         # decimated timestamps (200 Hz / 5 ms)
    'dec_info': {'decimation': 30, 'initial_dt': 0.000166, 'decimated_dt': 0.00498},
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

## WM Behavioral Data (sess_data_{sessid}.pkl)

pandas DataFrame, one row per trial. Protocol: `ToneCatDelayResp`.

### Common columns

| Column | Type | Description |
|--------|------|-------------|
| `sessid` | int | Session ID |
| `subjid` | int | Subject ID |
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

All event times (`cpoke_in_time`, `stim_start_time`, etc.) are **trial-relative seconds**
(Bpod resets to 0 at each trial start). `abs_tone_start_times` despite the "abs" prefix
means absolute within the trial, not session-absolute.

---

## Subjects

| subject_id | Species | Virus | Regions | WM sessions |
|------------|---------|-------|---------|-------------|
| 400 | Rattus norvegicus | AAV9 dLight 3.8 CAG | PL, NAc, DMS, DLS | 119247 |
| 238 | Rattus norvegicus | AAV9 dLight 3.8 CAG | NAc, DMS, DLS, TS | 124770 |

Sex, strain, and date of birth pending from Tanner (see open_questions.md).

### Implant coordinates (from fp_data_*.pkl → implant_info, mm re bregma)

**Subject 400**: PL right (+3.0, -0.6, -3.0) · NAc left (+1.6, +1.6, -7.2) ·
DMS right (+1.1, -2.1, -3.6) · DLS left (+0.6, +3.8, -3.8)

**Subject 238**: NAc right (+1.6, -1.6, -7.0) · DMS left (+1.1, +2.0, -3.6) ·
DLS right (+0.4, -3.8, -3.8) · TS left (-1.0, +3.8, -3.8)

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
                     (fallback: sessiondate + starttime from sess_data pkl)

FP NWB timestamp   = doric_time          (no offset; Doric IS the reference clock)
Behavioral event   = trial_start_ts[trial_i] + bpod_trial_relative_time
```

Pre-trial baseline (~12–15 s) has positive timestamps; first trial at `trial_start_ts[0]`.

---

## NWB Design

### FP data → ndx-fiber-photometry
- `FiberPhotometryTable`: one row per (region × wavelength) channel
- `FiberPhotometryResponseSeries` in `acquisition`: raw LockIn signals (from .doric)
- `FiberPhotometryResponseSeries` in `processing["ophys"]`: dFF signals (from pkl)
- `OpticalFiber` with `FiberInsertion` per implanted region (AP/ML/DV from pkl)

### Behavior → trials table
- `nwbfile.trials`: one row per trial, all scalar event times and outcomes
- Tone stimulus parameters as VectorData columns
- `TimeIntervals` for Bpod states if needed

### Video → external reference
- `ImageSeries(external_file=[...])` pointing to `mov_{sessid}.mp4`

---

## Status

- [x] Phase 1: Experiment discovery
- [x] Phase 2: Data inspection
- [ ] Phase 3: Metadata — awaiting Tanner's replies (see open_questions.md)
- [x] Phase 4: Synchronization analysis
- [ ] Phase 5: Code generation (backbone in place; interfaces to be implemented)
- [ ] Phase 6: Testing & validation
- [ ] Phase 7: DANDI upload
