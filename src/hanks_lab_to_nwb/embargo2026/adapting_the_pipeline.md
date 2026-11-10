# Adapting the conversion when the experiment changes

This guide covers what to edit when a session, the rig, the task or the preprocessing changes. For
each kind of change it says what the conversion handles on its own, what you have to edit, and
what happens if you don't.

Some mistakes stop the conversion with an error. Others produce a file that looks fine and is
wrong. Those are collected in
[Changes that convert without an error](#changes-that-convert-without-an-error); go through that
list after every change.

Installing the package and running a conversion are described in the
[README](../../../README.md).

## Terms

- FP: fiber photometry.
- AIN: an analog input channel of the Doric console (AIN01 to AIN04). Each one records one
  implanted fiber.
- Lock-in: the Doric acquisition mode that separates the two excitation wavelengths recorded on
  one AIN.
- iso and lig: the isosbestic (control) signal and the ligand-dependent (dLight) signal. The
  lab's preprocessing names its outputs with these, e.g. `raw_iso`, `raw_lig`.
- Session ID: the number in the source file names, written `{session_id}` below.

## What the conversion reads

Per session, from one data folder:

| File | Becomes | Required? |
|---|---|---|
| `sess_data_{session_id}.pkl` | Bpod task tables and `trials` | yes |
| `fp_data_{session_id}.pkl` | 12 processed FP series, artifact intervals, trial start times on the Doric clock, implant coordinates | yes |
| `Session_{session_id}.doric` | Raw lock-in series at about 6 kHz | no; without it the raw series are left out |
| `mov_{session_id}.mp4` | Behavior video | no; without it the video and the session epoch are left out |
| `mov_{session_id}.doric` | Frame times of the video | only when the mp4 is present |

Where the configuration lives:

| What | Where |
|---|---|
| Sessions (task, AIN to region), subjects, region names, time zone, Bpod protocol of each task | `metadata/sessions.yaml` |
| FP hardware: devices, wavelengths, filters, indicator, table rows, series names and descriptions | `metadata/fiber_photometry.yaml` |
| Experiment description, lab, institution, experimenter, keywords, publications, subject species and description | `metadata/general.yaml` |
| Session description and task description, per task | `metadata/wm_task.yaml`, `metadata/bandit_task.yaml` |
| Camera | `metadata/video.yaml` |
| Ontology terms for the institution, experimenter, species and brain regions | `metadata/external_resources.yaml` |
| Bpod events, actions, skipped states, excluded columns, column descriptions | `metadata/bpod_behavior_columns.yaml` |
| Source file names | `convert_session.py` and `convert_all_sessions.py` |

## Changes that convert without an error

The conversion does not stop for any of the changes below. It finishes, NWB Inspector passes, and
the file is wrong or incomplete. The linked section says what to check and edit.

| Change | What gets written |
|---|---|
| A region whose abbreviation is not under `regions` in `sessions.yaml` | The bare abbreviation as the `location`, and no ontology term. See [A new brain region](#a-new-brain-region). |
| A region with no entry in `fp_data["implant_info"]` | An optical fiber without insertion coordinates. See [A new session](#a-new-session-same-rig-and-task). |
| Different wavelengths, filters, LEDs or indicator | The old values from `fiber_photometry.yaml`. See [Different wavelengths, filters or indicator](#different-wavelengths-filters-or-indicator). |
| A processed signal in the pickle that is not one of the 12 listed | Nothing; the signal is left out. See [Changes to the FP preprocessing](#changes-to-the-fp-preprocessing). |
| Changed preprocessing parameters | The old numbers in the series descriptions. See [Changes to the FP preprocessing](#changes-to-the-fp-preprocessing). |
| A Bpod event name that is not in `bpod_behavior_columns.yaml` | An event type with `value="Unknown"`, and a warning. See [Changes to the Bpod task](#changes-to-the-bpod-task). |
| A new per-trial column | A `trials` column described as `"no description"`. See [Changes to the Bpod task](#changes-to-the-bpod-task). |
| A new per-trial column with `time` in its name | Values with the trial start time added, which is wrong for a duration. See [Changes to the Bpod task](#changes-to-the-bpod-task). |
| A missing value in a per-trial column | `False`, `0` or `"none"`, which cannot be told apart from a real value. See [Changes to the Bpod task](#changes-to-the-bpod-task). |
| A different camera setting, or another camera of the same model | The old values from `video.yaml`. See [Changes to the camera](#changes-to-the-camera). |

Some values exist only in the metadata files and have nothing in the source data to compare with:
the indicator and virus, the camera lens and pixel size, and the subject's sex, strain, date of
birth and weight. No check can detect a mistake there. Review `metadata/fiber_photometry.yaml`,
`metadata/video.yaml` and the `subjects` block of `metadata/sessions.yaml` for each new cohort.

These mistakes do stop the conversion with an error:

- a session or subject missing from `metadata/sessions.yaml`
- a session registered under the wrong task
- an AIN removed from `ain_to_region` but still described in `fiber_photometry.yaml`
- a listed processed signal or raw stream that is missing from the source file
- a camera whose model differs from the one in `DORIC_CAMERA_TIME_PATH`

## A new session, same rig and task

Handled automatically:

- recording length, sample count, trial count
- whether the raw FP clock is stored as timestamps or as a rate
- which optional files are present
- dropouts and range edges, read from `fp_data`
- implant coordinates, read from `fp_data["implant_info"]`

You edit `metadata/sessions.yaml`:

```yaml
sessions:
  125000:
    task: wm_task                                      # or bandit_task
    ain_to_region: { 1: NAc, 2: DMS, 3: TS, 4: DLS }   # from Subj Info.txt
subjects:                                              # only for a new rat
  512:
    sex: M
    strain: Long Evans
    date_of_birth: "2025-08-01"
    weight: 500 g
```

The AIN to region mapping changes from session to session, even for the same rat. Take it from
that session's `Subj Info.txt` entry, never from an earlier session.

If you don't:

- `convert_session.py` stops with an error that names the missing session or subject and the
  file to add it to.
- `convert_all_sessions.py` converts the registered sessions and prints a `NOT CONVERTED` line
  listing the sessions in the data folder that are not registered. Read that line.
- A session registered under the wrong task stops with an error: the Bpod protocol in
  `sess_data` is checked against the `protocol` of the task in `sessions.yaml`.

Check the implant coordinates. A region that has no entry in `fp_data["implant_info"]` is written
without insertion coordinates and without a message. Open the converted file and confirm that
every optical fiber has them. If one is missing, the region has to be added to `implant_info` by
whoever produces the pickle.

## A new brain region

Handled automatically: any region abbreviation that `fp_data` uses as a key.

You edit:

- `regions` in `metadata/sessions.yaml`, adding e.g. `VTA: Ventral tegmental area`.
- `anatomical_structures` in `metadata/external_resources.yaml`, adding the ontology term under
  the same full name.

If you don't: the conversion succeeds. The table `location` and the device descriptions state the
bare abbreviation (`VTA`) where the other regions have the full name, and the region gets no
ontology term. Device names are not affected; they always use the abbreviation.

## More or fewer fibers

`fiber_photometry.yaml` describes exactly four fibers, AIN01 to AIN04: 8 table rows, 4 optical
fibers, 8 excitation filters, 4 photodetectors, and 4 raw stream names per wavelength. The
processed series build their columns from `ain_to_region`, but the table rows and devices do not
adapt.

Fewer fibers (e.g. AIN04 unused): dropping the AIN from `ain_to_region` alone makes the conversion
fail at metadata validation, because the unused AIN's devices never get a name. Also remove the
unused AIN from `fiber_photometry.yaml`:

- the `iso_` and `sig_` rows
- `optical_fiber_ain0X`, `excitation_filter_*_ain0X` and `photodetector_ain0X`
- both raw series' `stream_names`
- every series' `fiber_photometry_table_region` list

More fibers (AIN05 and up): add the same entries for the new AIN. The code assumes a single-digit
AIN (`int(stream_name[-1])` in `interfaces/processed_fiber_photometry_interface.py`), so AIN10 and
up need a code change.

## Different wavelengths, filters or indicator

Nothing compares `fiber_photometry.yaml` with the `.doric` file. If you forget to update the YAML,
the conversion succeeds and the file states the old wavelengths.

You edit `metadata/fiber_photometry.yaml`:

- `excitation_wavelength_in_nm` and `emission_wavelength_in_nm` on each table row
- the LED models' `wavelength_range_in_nm` and descriptions
- the excitation and emission filter models: `center_wavelength_in_nm`, `bandwidth_in_nm`
- `FiberPhotometryIndicators`, for a new sensor
- the raw `stream_names`, if the lock-in layout changes. Today isosbestic is on AOUT01 and AOUT03
  and signal on AOUT02 and AOUT04. A stream name that is not in the file fails the conversion with
  a `KeyError` when the data is read.

Also edit the text that names the wavelengths or the sensor:

- the `description` and `fiber_photometry_table_region_description` of the raw and processed
  series in `fiber_photometry.yaml` ("~415/420 nm", "490 nm", "dLight3.8")
- `session_description` in both task YAMLs, and `experiment_description` and `Subject.description`
  in `metadata/general.yaml`

The lab's `processed_signals` are keyed by role (`raw_lig`, `raw_iso`, and so on), not by
wavelength, so the processed series need no change.

## Changes to the FP preprocessing

Handled automatically:

- the decimated time base and rate, read from `fp_data["fp_data"]["time"]`
- dropouts, independent ranges and the pre-session crop, read from `processing_info` into the
  `invalid_times` table
- per-fiber `comments`, written to the FP table's `notes` column

New or renamed processed signals (e.g. a z-score). Add or change the signal in two places:

1. `PROCESSED_SIGNALS` in `nwbconverter.py`, the one list of signals in the code
2. a series entry in `metadata/fiber_photometry.yaml`, with its name, description and
   `fiber_photometry_table_region_description`. Write `{regions}` in the latter where the
   session's region names should appear.

A signal in the pickle that is not listed is left out of the file without a message. To find one,
compare the keys of `fp_data["fp_data"]["processed_signals"][region]` with `PROCESSED_SIGNALS`. A
listed signal that is missing from the pickle raises a `KeyError`.

Changed parameters (`pre_lpf`, `baseline_lpf`, `iso_bands`, the decimation factor). These are not
read from the pickle. They are fixed text in the series descriptions in `fiber_photometry.yaml`
("10 Hz", "~0.0005 Hz", the band edges, "30×"). If the preprocessing changes them, the file is
written with the old numbers. Compare `fp_data["fp_data"]["processing_info"]` with the series
descriptions and update the text.

## Changes to the Bpod task

Most task changes are picked up from the data. The table lists what happens for each and what to
edit in `metadata/bpod_behavior_columns.yaml`.

| Change | What happens | Edit |
|---|---|---|
| New per-trial column | Added to `trials`, type inferred, description `"no description"` | Add a `description` under `columns:` |
| New column whose name contains `time` | `trial_start_ts` is added to every value to put it on the Doric clock, unless the name starts with `rel_` | Decide whether the column is a time within the trial or a duration. For a duration or latency (e.g. `hold_time`) set `abs_time: false`, otherwise the values are wrong |
| Column that is empty for the whole session | Left out | none |
| Column that is a scalar in some sessions and a list in others | Type inferred per session, so sessions disagree | Set `dtype:` (e.g. `list_float`) |
| Missing value in a column | Written as `False` for a bool, `0` for an int, `"none"` for a string; a float is written as NaN | For an int or string column set `none_value:` to a value that cannot occur. A bool has no such option |
| New Bpod state | Added to `StateTypesTable` | none |
| New port (e.g. `Port4In`) or other animal event | Stored as its own event type with `value="Unknown"`, with a warning | Add under `events:`, e.g. `Port4In: {event_name: Port4, value: "In"}` |
| New machine output (e.g. `BNC2High`, `GlobalTimer4_End`) | Stored as an event with `value="Unknown"`, not as an action | Add under `actions:` |
| Different sync word (e.g. 16 bits) | The extra `GenerateTrialBit16` state is written as a behavioral state | Add it to `states_to_skip` |

The warning for unknown event names is easy to miss in a batch run. Search the conversion output
for "Unmapped Bpod event names".

A new protocol needs three steps:

1. Create `metadata/<task>.yaml` with its session description and task description.
2. Add `<task>` with its Bpod `protocol` under `tasks:` in `metadata/sessions.yaml`.
3. Register the sessions under it.

A different Bpod model: the device name and description are set in `get_metadata` of
`BpodBehaviorInterface` (`interfaces/bpod_behavior_interface.py`).

What the interface expects from the lab's preprocessing:

- `sess_data` as a DataFrame with one row per trial and a `parsed_events` dict of `States` and
  `Events`, in Bpod's trial-relative seconds
- `fp_data["fp_data"]["trial_start_ts"]` with at least one entry per trial, which the interface
  checks

A change to that structure or a different synchronization scheme needs code changes in
`bpod_behavior_interface.py`. That includes reading Bpod's `.mat` files directly, or dropping the
DIO01 trial word.

## Changes to the camera

You edit `metadata/video.yaml`:

- the model, serial number and description of the camera
- `frame_rate`
- `lens` and `meters_per_pixel`, which are still placeholders (`unknown` and `0.0`)

Keep the device name in the form `camera_device <id>`. Spyglass reads the camera ID from it.

Nothing compares `video.yaml` with the recording. To check it, compare it with the attributes of
`mov_{session_id}.doric`: `Configurations/BehaviorCamera` (`DeviceName`, `SerialNumber`) and
`Configurations/BehaviorCamera/Settings` (`FPS`, `ResolutionWidth`, `ResolutionHeight`).

A different camera model also needs a code change. `SpyglassVideoInterface` reads the frame times
from a path that contains the model, `DORIC_CAMERA_TIME_PATH` in
`interfaces/spyglass_video_interface.py`:
`DataAcquisition/BehaviorCamera/Video/Series0001/DMK-33UX290/Time`. A different model fails there
with a `KeyError`.

More than one camera needs changes in the same interface and in `convert_session.py`, which passes
a single mp4 and sets `camera_id` to `[0]`.

## Other changes

| Change | Edit |
|---|---|
| New experimenter, lab, institution, keywords or publication | `metadata/general.yaml`. For a new experimenter or institution also add the ORCID or ROR in `metadata/external_resources.yaml` |
| The rig moves to another time zone | `timezone` in `metadata/sessions.yaml` |
| The source files are named differently | The file names built in `session_to_nwb` (`convert_session.py`) and the `sess_data_*.pkl` pattern in `get_session_ids` (`convert_all_sessions.py`) |

## After any change

1. Convert one session as a stub. In the `__main__` block at the bottom of `convert_session.py`
   set `session_id`, the two paths and `stub_test = True`, then run the file. It writes to
   `nwb_stub/` inside the output folder in seconds.
2. Run `nwbinspector <output folder> --config dandi`.
3. Go through
   [Changes that convert without an error](#changes-that-convert-without-an-error).
4. Open the file in `tutorials/bpod_demo.ipynb`, `tutorials/doric_fp_demo.ipynb` or
   `tutorials/processed_fp_demo.ipynb` and check the FP table, the region labels and the `trials`
   columns. Each notebook opens `nwb_output/sub-400_ses-119247.nwb`; change the path at the top to
   your file.
5. With `convert_all_sessions.py`, read the "Converting N sessions" and `NOT CONVERTED` lines and
   check the `exceptions/` folder in the output folder. A session that fails writes its traceback
   there and does not stop the batch.
6. For a new rig or synchronization setup, check that Bpod trial starts land on the DIO01 pulses
   and that cue responses come after their cues.
