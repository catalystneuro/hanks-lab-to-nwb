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
| FP processed (dFF) | Python pickle `.pkl` | `fp_data_{sessid}.pkl` | `ProcessedFiberPhotometryInterface` (follow-up PR) |
| Behavioral data | Python pickle `.pkl` | `sess_data_{sessid}.pkl` | `BanditBehaviorInterface` / `WMBehaviorInterface` (follow-up PR) |
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
| `block_prob` | float | Reward probability of the chosen port for this block |
| `p_reward_left` | float | Reward probability of left port this trial |
| `p_reward_right` | float | Reward probability of right port this trial |
| `high_port` | str | Port with higher reward probability (`'left'` or `'right'`) |
| `high_side` | str | Same as high_port (alternative column name) |
| `forced_choice` | bool | Forced choice trial (only one port active) |
| `viol` | bool | Protocol violation (e.g. premature withdrawal) |
| `epoch_schedule` | str | Volatility epoch schedule name |
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

All event times are **trial-relative seconds** (Bpod resets to 0 at each trial start).

---

## Subjects

| subject_id | Sex | Strain | DOB | Weight | Species | Virus | Regions |
|------------|-----|--------|-----|--------|---------|-------|---------|
| 400 | M | Long Evans | 2024-03-19 | 530 g | Rattus norvegicus | AAV9-CAG-dLight3.8 (UNC) | PL, NAc, DMS, DLS |
| 238 | M | Long Evans | 2025-05-?? ⚠️ | 540 g | Rattus norvegicus | AAV9-CAG-dLight3.8 (UNC) | NAc, DMS, DLS, TS |

⚠️ Subject 238 DOB: lab reported `2025-05-0` — using `2025-05-01` as placeholder until confirmed.

**Experimenter**: Stevenson, Tanner

### Sessions (from Subj Info.txt)

| session_id | subject_id | Task | AIN→region mapping |
|------------|------------|------|--------------------|
| 119247 | 400 | WM | 1→DLS, 2→PL, 3→DMS, 4→NAc |
| 119974 | 400 | Bandit | 1→NAc, 2→PL, 3→DLS, 4→DMS |
| 124770 | 238 | WM | 1→DMS, 2→DLS, 3→TS, 4→NAc |
| 124949 | 238 | Bandit | 1→NAc, 2→DMS, 3→TS, 4→DLS |

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
- `FiberPhotometryResponseSeries` in `processing["ophys"]`: dFF signals (from pkl) — follow-up PR
- `OpticalFiber` with `FiberInsertion` per implanted region (AP/ML/DV from pkl)

### Behavior → trials table (follow-up PR)
- `nwbfile.trials`: one row per trial, all scalar event times and outcomes
- Bandit: block structure, reward probabilities, epoch columns
- WM: tone timing, tone category, delay, correct port columns

### Video → external reference (follow-up PR)
- `ImageSeries(external_file=[...])` pointing to `mov_{sessid}.mp4`

---

## Status

- [x] Phase 1: Experiment discovery
- [x] Phase 2: Data inspection
- [x] Phase 3: Metadata
- [x] Phase 4: Synchronization analysis
- [ ] Phase 5: Code generation
- [ ] Phase 6: Testing & validation
- [ ] Phase 7: DANDI upload
