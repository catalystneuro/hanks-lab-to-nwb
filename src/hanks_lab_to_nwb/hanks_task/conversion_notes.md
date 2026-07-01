# Hanks Lab → NWB Conversion Notes

## Experiment Overview

The Hanks lab records behavioral and fiber photometry data to study the neural basis of
decision-making and working memory in rats. Two experimental protocols are run:

1. **ToneCatDelayResp (WM)** — Auditory working memory delay response task: rats hear 1-2
   tones during a stimulus window and must remember the relevant tone category to poke the
   correct port after a delay.
2. **ClassicRLTasks / BasicRLTasks (Bandit)** — Two-arm bandit task: rats track reward
   probabilities across left/right ports that switch contingencies across blocks.

Behavioral events (Bpod-controlled): center port LED cue, center port pokes (in/out),
auditory stimuli, response cue (LED off), side port choice, reward delivery.

Fiber photometry: dLight 3.8 (dopamine indicator) recorded with Doric system from up to
4 brain regions simultaneously per session. Five target regions across subjects: PL
(prelimbic cortex), NAc (nucleus accumbens), DMS (dorsomedial striatum), DLS (dorsolateral
striatum), TS (tail of striatum).

**Lab contact:** Tanner Stevenson (point person), Professor Tim Hanks (PI)
**GitHub target:** https://github.com/catalystneuro/hanks-lab-to-nwb (not yet created on GitHub)
**Goals:** NWB conversion for DANDI publication + Spyglass ingestion (ARC project)

---

## Data Streams

| Stream | Format | Source | File Pattern | NeuroConv Interface |
|--------|--------|--------|-------------|---------------------|
| FP raw (LockIn signals) | Doric HDF5 `.doric` | Doric FPConsole | `Session_{sessid}.doric` | **Custom DoricFiberPhotometryInterface** |
| FP processed (dFF, fitted iso, etc.) | Python pickle `.pkl` | Lab preprocessing pipeline | `fp_data_{sessid}.pkl` | **Custom (optional, from pkl)** |
| Behavioral data | Python pickle `.pkl` (from SQL DB) | Bpod → SQL → Python export | `sess_data_{sessid}.pkl` | **Custom BpodBehaviorInterface** |
| Video | `.mp4` | Doric camera | `mov_{sessid}.mp4` | ExternalVideoInterface |
| Video (Doric embedded) | Doric HDF5 `.doric` | Doric camera | `mov_{sessid}.doric` | (skip — use MP4) |
| Pose estimation | TBD (DLC/SLEAP) | Future | TBD | DeepLabCutInterface or SLEAPInterface |

---

## Doric File Structure (Session_119247.doric)

```
DataAcquisition/FPConsole/Signals/Series0001/
  AnalogIn/
    AIN01, AIN02, AIN03, AIN04  shape=(26,654,952,) float64  — raw photodetector voltages
    Time                          shape=(26,654,952,) float64  — starts at 0.0s
  AnalogOut/
    AOUT01-04                     shape=(26,654,952,) float64  — excitation LED drive signals
    Time
  DigitalIO/
    DIO01                         shape=(26,654,952,) float64  — Bpod TTL sync signal (binary)
    DIO04
    Time                          starts at 0.0s
  LockInAOUT01/
    AIN01  Username='Ch1_420'     shape=(26,653,687,) float64  — Ch1 (e.g. DLS) @ 420nm (isosbestic)
    AIN02  Username='Ch2_420'     shape=(26,653,687,) float64  — Ch2 (e.g. PL) @ 420nm
    Time   starts at 0.0831s, dt=0.000166s (~6016 Hz), ends at 4424.595s
  LockInAOUT02/
    AIN01  Username='Ch1_490'     — Ch1 @ 490nm (ligand)
    AIN02  Username='Ch2_490'     — Ch2 @ 490nm
    Time
  LockInAOUT03/
    AIN03  Username='Ch3_420'     — Ch3 @ 415nm (iso; NOTE: username may say 420 but actual λ is 415nm per SubjInfo)
    AIN04  Username='Ch4_420'     — Ch4 @ 415nm
    Time
  LockInAOUT04/
    AIN03  Username='Ch3_490'     — Ch3 @ 490nm (ligand)
    AIN04  Username='Ch4_490'     — Ch4 @ 490nm
    Time
```

**OPEN QUESTION:** The Doric LockInAOUT03 username says "Ch3_420" but Subj Info says AOUT03
wavelength is 415nm. Need to confirm with Tanner whether the file username is mislabeled.
We will use the wavelength from Subj Info (the ground truth), not the username in the file.

### Timing

- LockIn channels: 26,653,687 samples at 0.000166s per sample (≈ 6016 Hz)
- Total duration: ~4424 seconds (73.7 minutes)
- DigitalIO time starts at 0.0s, LockIn time starts at ~0.083s

### Channel-Region Mapping (per session, from Subj Info.txt)

Each session has a metadata dict specifying:
- `FP Input Channel Region Mapping`: {region: AIN_number}
- `FP Output Channel Wavelengths`: {AOUT_number: wavelength_nm}
- `FP Input/Output Channel Mapping`: {AIN_number: [AOUT_numbers_it_connects_to]}

Example for session 119247 (Subject 400):
```
FP Input Channel Region Mapping: {'DLS': 1, 'PL': 2, 'DMS': 3, 'NAc': 4}
FP Output Channel Wavelengths: {1: 420, 2: 490, 3: 415, 4: 490}
FP Input/Output Channel Mapping: {1: [1,2], 2: [1,2], 3: [3,4], 4: [3,4]}
```

→ DLS (AIN01) is measured at 420nm (LockInAOUT01/AIN01) and 490nm (LockInAOUT02/AIN01)
→ PL (AIN02) is measured at 420nm (LockInAOUT01/AIN02) and 490nm (LockInAOUT02/AIN02)
→ DMS (AIN03) is measured at 415nm (LockInAOUT03/AIN03) and 490nm (LockInAOUT04/AIN03)
→ NAc (AIN04) is measured at 415nm (LockInAOUT03/AIN04) and 490nm (LockInAOUT04/AIN04)

### Bpod TTL Sync (DIO01)

- DIO01 encodes trial numbers in binary using 15 bits at 1ms pulse width
- First pulse marks trial start; subsequent pulses encode the trial number
- `acq_utils.parse_trial_times()` decodes this encoding
- Trial start timestamps from DIO01 link Doric time → Bpod time

---

## Processed FP Data (fp_data_{sessid}.pkl)

Structure:
```python
{
  'fp_data': {
    'trial_start_ts': (166,) float64,   # trial start times in Doric clock (seconds)
    'time': (888457,) float64,          # decimated timestamp array
    'dec_info': {'decimation': 30, 'initial_dt': 0.000166, 'decimated_dt': 0.00498},
    'raw_signals': {
      'DLS': {'420': (888457,), '490': (888457,)},
      'PL':  {'420': (888457,), '490': (888457,)},
      'DMS': {'415': (888457,), '490': (888457,)},
      'NAc': {'415': (888457,), '490': (888457,)},
    },
    'processed_signals': {
      'DLS': {
        'raw_lig': (888457,), 'raw_iso': (888457,),
        'filtered_lig': (888457,), 'filtered_iso': (888457,),
        'baseline_lig': (888457,), 'baseline_iso': (888457,),
        'baseline_corr_lig': (888457,), 'baseline_corr_iso': (888457,),
        'fitted_iso': (888457,),
        'dff_iso': (888457,),                 # isosbestic-corrected ΔF/F
        'dff_iso_baseline_fband': (888457,),  # alternative ΔF/F method
        'iso_fit_info': {...},
        'lig': '490', 'iso': '420',
      },
      # same for PL, DMS, NAc
    },
    'comments': {'DLS': '', ...},
    'fpids': {'DLS': 10191, ...},
  },
  'implant_info': {
    'DLS': {'side': 'left', 'AP': 0.6, 'ML': 3.8, 'DV': -3.8, 'fiber_type': 'Flat 400μm optical fiber'},
    ...
  },
  'subj_id': 400,
  'sess_id': 119247,
}
```

Decimation: 30× (from ~6016 Hz to 200 Hz / 5ms). Timestamps are midpoint of each bin.

**Plan**: Store both raw LockIn signals from `.doric` AND processed signals from `.pkl`.
Per project spec: "Raw fluorescence traces and the results of DF/F calculation will both be included."

---

## Behavioral Data (sess_data_{sessid}.pkl)

A pandas DataFrame with one row per trial.

### Common columns (both protocols)

| Column | Description |
|--------|-------------|
| `sessid` | Session ID (integer) |
| `subjid` | Subject ID (integer) |
| `sessiondate` | `datetime.date` |
| `starttime` | `pandas.Timedelta` (time of day) |
| `protocol` | Protocol name string |
| `trial` | Trial number (1-indexed) |
| `trialtime` | `pandas.Timestamp` of trial start (wall clock) |
| `parsed_events` | Dict with `States` (name → [start, end, ...]) and `Events` (name → [timestamps]) in Bpod seconds |
| `hit` | bool — animal made a valid response |
| `reward` | int — reward volume (0 if unrewarded) |
| `choice` | str — 'left', 'right', or 'none' |
| `cpoke_in_time` | float — center port in time (Bpod seconds, relative to **session start**) |
| `cpoke_out_time` | float — center port out time |
| `stim_start_time` | float — stimulus start time |
| `response_cue_time` | float — response cue time |
| `response_time` | float — side port poke time |
| `reward_time` | float — reward delivery time |
| `RT` | float — reaction time |

### WM-only columns (ToneCatDelayResp)

| Column | Description |
|--------|-------------|
| `bail` | bool — animal withdrew before response |
| `n_tones` | int — number of tones in sequence |
| `stim_dur` | float — stimulus duration (s) |
| `rel_tone_start_times` | float — tone start time relative to stim_start_time |
| `abs_tone_start_times` | float — tone start time in session seconds |
| `abs_tone_end_times` | float — tone end time |
| `tone_info` | list of str — tone categories heard (e.g. ['high', 'low']) |
| `correct_port` | str — 'left' or 'right' |
| `cport_on_time` | float — center port LED on time |
| `cue_start_time`, `cue_end_time` | float — response cue window |

### Bandit-only columns (ClassicRLTasks)

| Column | Description |
|--------|-------------|
| `viol` | bool — protocol violation |
| `block_num` | int — block number |
| `block_trial` | int — trial within block |
| `p_reward_left`, `p_reward_right` | float — reward probability per side |
| `high_port` | str — which port has higher prob |
| `forced_choice` | bool — forced choice trial |
| `epoch_schedule`, `epoch_label` | str — volatility epoch info |

### Timing notes

- All times are in **seconds relative to session start** (Bpod clock)
- `sessiondate` + `starttime` give the absolute wall-clock session start
- Bpod time is separate from Doric time; synchronization is via DIO01 TTL signal
- Linking: `trial_start_ts` in fp_data (Doric seconds) matches `cpoke_in_time` in sess_data

### Bpod State Machine (WM trial, session 119247 trial 1)

Key states (in session-relative seconds):
- `ITI`: [0.016, 5.016] — inter-trial interval
- `WaitForCenterPoke`: [5.016, 227.341] — waiting for rat to initiate
- `Stimulus`: [227.35, 232.17] — tone presentation period (multiple sub-states)
- `CueResponse`: [232.17, 232.80] — response window
- `Hit/Error/Bail`: outcome state

Key events: `Port1In/Out`, `Port2In/Out`, `Port3In/Out` (center, left?, right?), `BNC1High/Low` (sync)

**OPEN QUESTION:** Confirm port assignments: which port number corresponds to which physical
location (center, left side, right side)? Likely Port2=center, Port1 and Port3=sides.
Need to confirm with Tanner.

---

## Subjects

| subject_id | Species | Virus | Regions | Sessions provided |
|------------|---------|-------|---------|-------------------|
| 400 | Rattus norvegicus | AAV9 dLight 3.8 CAG | PL, NAc, DMS, DLS | 119247 (WM), 119974 (Bandit) |
| 238 | Rattus norvegicus | AAV9 dLight 3.8 CAG | NAc, DMS, DLS, TS | 124770 (WM), 124949 (Bandit) |

Implant coordinates from Subj Info.txt (see file for full AP/ML/DV values, all 400μm flat fibers).

**OPEN QUESTIONS for Tanner:**
- [ ] Sex and date of birth for each subject
- [ ] Exact strain / genotype (e.g. Long-Evans, Sprague-Dawley)
- [ ] Timezone of acquisition system (for session_start_time UTC offset)
- [ ] Confirm port number assignments (Port1/2/3 → center/left/right)
- [ ] LockInAOUT03 username says "Ch3_420" but Subj Info says 415nm — confirm actual wavelength
- [ ] What is DIO04 used for?
- [ ] Is there a published paper or preprint? DOI?
- [ ] How many total subjects and sessions in the full dataset?
- [ ] Where is the SQL database hosted? Can we access raw SQL exports instead of pkl files?

---

## Directory Structure

```
Google Drive (mounted at ~/source_data/hanks-lab/):
├── acq_utils.py              — Doric data acquisition utilities
├── base_db.py                — base database class
├── basicRLtasks_db.py        — Bandit task database class
├── doric_utils.py            — Doric HDF5 reading utilities
├── fp_analysis_helpers.py    — FP analysis tools
├── fp_utils.py               — FP signal processing utilities
├── package_fp_data.py        — GUI script to package Doric data → SQL DB
├── tonecatdelayresp_db.py    — WM task database class
└── For Catalyst Neuro/       — sample data for 4 sessions
    ├── Session_119247.doric  — raw FP acquisition (subj400, WM)
    ├── Session_119974.doric  — raw FP acquisition (subj400, Bandit)
    ├── Session_124770.doric  — raw FP acquisition (subj238, WM)
    ├── Session_124949.doric  — raw FP acquisition (subj238, Bandit)
    ├── fp_data_119247.pkl    — processed FP data (decimated + dFF)
    ├── fp_data_119974.pkl
    ├── fp_data_124770.pkl
    ├── fp_data_124949.pkl
    ├── sess_data_119247.pkl  — behavioral trial data (from SQL)
    ├── sess_data_119974.pkl
    ├── sess_data_124770.pkl
    ├── sess_data_124949.pkl
    ├── mov_119247.doric      — video embedded in Doric file
    ├── mov_119247.mp4        — standalone video
    ├── mov_119974.doric/mp4
    ├── mov_124770.doric/mp4
    ├── mov_124949.doric/mp4
    └── Subj Info.txt         — subject and session FP channel mapping metadata
```

---

## Sessions (sample)

| sess_id | subj_id | Task | sessiondate | n_trials |
|---------|---------|------|-------------|----------|
| 119247 | 400 | WM | 2025-10-02 | 165 |
| 119974 | 400 | Bandit | 2025-10-20 | 304 |
| 124770 | 238 | WM | ~2025 | TBD |
| 124949 | 238 | Bandit | ~2025 | TBD |

Full dataset scale: unknown — need to ask Tanner how many subjects/sessions total.

---

## Existing Resources

- **Publication**: Not yet published (ARC project in progress)
- **Existing public data**: None
- **Analysis code**: Provided on Google Drive (Python scripts above)
- **Existing data readers**: `doric_utils.py`, `acq_utils.py`, `fp_utils.py` — will be reused
- **Data source**: Google Drive `1hW0vnNGzJ6lkzNMe1edjffPchdpJY0wA` → mounted at `~/source_data/hanks-lab/`

---

## Synchronization Plan

1. Doric DIO01 TTL → `acq_utils.parse_trial_times()` → trial start timestamps in Doric time
2. Match to `trial_start_ts` from fp_data pkl (already computed by lab)
3. Behavioral times (`cpoke_in_time`, etc.) are in Bpod seconds relative to session start
4. Alignment: `t_nwb = t_bpod + (doric_trial_start_ts[0] - bpod_trial_start_t[0])`
   (or per-trial alignment if clock drift is significant)
5. Session start time in NWB: `sessiondate + starttime` (need timezone from Tanner)

---

## NWB Design Plan

### FP Data → ndx-fiber-photometry extension

Will use the `ndx-fiber-photometry` NWB extension for storing fiber photometry data:
- `FiberPhotometry` object per channel (region × wavelength combination)
- `FiberPhotometryResponseSeries` for each signal trace
- Store raw decimated signals (from .doric, decimated to 200 Hz)
- Store processed dFF signals (from fp_data pkl)
- Store artifact time windows as `TimeIntervals` ("FP_Artifacts")
- Store implant coordinates as `OpticalFiber` objects with AP/ML/DV metadata

### Behavior → Trials table + Events

- `nwbfile.trials` table: one row per trial, with columns for all scalar events and outcomes
- `TimeSeries` or `AnnotationSeries` for per-port event timestamps if needed
- `TimeIntervals` for behavioral states (ITI, Stimulus, CueResponse, etc.)

### Video → External reference

- `ImageSeries` with `external_file` pointing to MP4 files

### Subject metadata

- `nwbfile.subject` with subject_id, species, sex, age, description (genotype/virus)

---

## Conversion Interface Plan

| Interface | Input | Output NWB objects |
|-----------|-------|-------------------|
| `DoricFiberPhotometryInterface` | `.doric` HDF5 + Subj Info metadata | Raw FP traces, FiberPhotometry metadata |
| `FPProcessedInterface` | `fp_data_*.pkl` | Processed signals (dFF, fitted_iso) |
| `BpodBehaviorInterface` (WM) | `sess_data_*.pkl` | Trials table, event timestamps |
| `BpodBehaviorInterface` (Bandit) | `sess_data_*.pkl` | Trials table, block info |
| `ExternalVideoInterface` | `mov_*.mp4` | ImageSeries (external ref) |
| Future: `DeepLabCutInterface` | DLC output | PoseEstimation (ndx-pose) |

---

## Status

- [x] Phase 1: Experiment discovery
- [ ] Phase 2: Data inspection (in progress)
- [ ] Phase 3: Metadata collection (open questions above)
- [ ] Phase 4: Synchronization analysis
- [ ] Phase 5: Code generation
- [ ] Phase 6: Testing & validation
- [ ] Phase 7: DANDI upload
