# hanks-lab-to-nwb

Conversion of Hanks lab fiber photometry and behavior data to the
[Neurodata Without Borders](https://nwb-overview.readthedocs.io/) (NWB) format, built on
[NeuroConv](https://neuroconv.readthedocs.io/).

Each session becomes one NWB file containing:

- the raw fiber photometry acquisition from the Doric console
- the 12 processed fiber photometry signals from the lab's preprocessing, and the time windows
  in which each region's signal is not usable
- the Bpod behavior: states, events, actions and the trials table, on the Doric clock
- a link to the behavior video, with one timestamp per frame
- hardware, subject and session metadata, with ontology identifiers for the institution,
  experimenter, species and brain regions

The files can also be loaded into a [Spyglass](https://github.com/LorenFrankLab/spyglass)
database; see [spyglass/README.md](spyglass/README.md).

## Installation

The conversion is installed from this repository with [uv](https://docs.astral.sh/uv/)
([installation instructions](https://docs.astral.sh/uv/getting-started/installation/)). You also
need `git` ([installation instructions](https://github.com/git-guides/install-git)).

```bash
git clone https://github.com/catalystneuro/hanks-lab-to-nwb
cd hanks-lab-to-nwb
uv sync
```

`uv sync` creates a virtual environment in `.venv` and installs the exact package versions recorded
in `uv.lock`, which are the versions the conversion was tested with. The package itself is
installed in editable mode, so changes you make to the source code take effect without
reinstalling.

Installing with plain `pip install .` is not supported. `ndx-franklab-novela` 0.2.4 declares
`hdmf<5` while `pynwb` 4 needs `hdmf>=6.2`, and only uv applies the override in `pyproject.toml`
that reconciles them.

To update the dependencies later, edit `pyproject.toml`, run `uv lock`, and commit the new
`uv.lock`.

## Source data

All sessions are read from one folder. The number in each file name is the session ID.

| File | Content | Required |
|---|---|---|
| `sess_data_{session_id}.pkl` | Bpod trials, one row per trial | yes |
| `fp_data_{session_id}.pkl` | Processed fiber photometry, trial start times, implant coordinates | yes |
| `Session_{session_id}.doric` | Raw fiber photometry acquisition | no |
| `mov_{session_id}.mp4` | Behavior video | no |
| `mov_{session_id}.doric` | Frame times of the video | only with the mp4 |

The two `.pkl` files are pickled Python objects. The environment that runs the conversion must
have a pandas version that can read the pickles written by the preprocessing environment.

## Converting a session

Every session has to be registered before it can be converted. Open
`src/hanks_lab_to_nwb/embargo2026/metadata/sessions.yaml` and add the session with its task and
its AIN to region mapping, and the subject if the rat is new. The comments in that file explain
each field.

To convert one session, edit the four values in the `__main__` block at the bottom of
`src/hanks_lab_to_nwb/embargo2026/convert_session.py` (`session_id`, `data_dir_path`,
`output_dir_path`, `stub_test`) and run it:

```bash
uv run python src/hanks_lab_to_nwb/embargo2026/convert_session.py
```

With `stub_test = True` only the first samples of each series are written, to a `nwb_stub` folder
inside the output folder. It takes seconds and is the quickest way to check a change.

To convert every registered session found in the data folder:

```bash
uv run python src/hanks_lab_to_nwb/embargo2026/convert_all_sessions.py <data_dir_path> <output_dir_path>
```

Add `--stub_test` for a quick check and `--max_workers N` to convert N sessions in parallel. The
script prints the sessions it converts, and a `NOT CONVERTED` line listing sessions in the folder
that are not registered. A session that fails writes its error to an `exceptions` folder inside
the output folder and does not stop the others.

The output file is named `sub-{subject_id}_ses-{session_id}.nwb`. It stores the location of the
mp4 as a path relative to the NWB file. If you move the NWB file, move the video so that the
relative location stays the same.

## Checking the output

Run [NWB Inspector](https://nwbinspector.readthedocs.io/) on the output folder:

```bash
uv run nwbinspector <output_dir_path> --config dandi
```

Three best-practice suggestions are expected for every file and come from the layout Spyglass
needs: the processing module named `tasks`, the single-row `epochs` table and the single-row
`task_table`.

The notebooks in `src/hanks_lab_to_nwb/tutorials` show how to read a converted file:

| Notebook | Shows |
|---|---|
| `doric_fp_demo.ipynb` | Raw fiber photometry and the hardware metadata |
| `processed_fp_demo.ipynb` | Processed fiber photometry signals |
| `bpod_demo.ipynb` | Bpod states, events, actions and trials |
| `dandi_001973_demo.ipynb` | Streaming a file from the DANDI Archive |

The first three open a local file; change the path at the top of the notebook to your own. The
notebooks need `jupyter`, which is not part of the conversion environment.

## When the experiment changes

[adapting_the_pipeline.md](src/hanks_lab_to_nwb/embargo2026/adapting_the_pipeline.md) says what to
edit for a new session, brain region, fiber count, wavelength, preprocessing step, Bpod task or
camera, and how to start a new experiment. Read its section "Changes that convert without an
error" after any change to the rig, the task or the preprocessing: it lists the mistakes the
conversion cannot detect.

## Repository structure

    hanks-lab-to-nwb/
    ├── pyproject.toml                  dependencies
    ├── uv.lock                         exact versions installed by `uv sync`
    ├── spyglass/                       loading converted files into Spyglass
    └── src/hanks_lab_to_nwb/
        ├── embargo2026/                the WM and bandit task experiment
        │   ├── convert_session.py          converts one session
        │   ├── convert_all_sessions.py     converts every registered session in a folder
        │   ├── nwbconverter.py             the interfaces that make up a session
        │   ├── metadata/
        │   │   ├── sessions.yaml               sessions, subjects, regions, time zone
        │   │   ├── general.yaml                lab, experimenter, experiment description
        │   │   ├── wm_task.yaml                session and task description, WM task
        │   │   ├── bandit_task.yaml            session and task description, bandit task
        │   │   ├── fiber_photometry.yaml       fiber photometry hardware and series
        │   │   ├── video.yaml                  camera
        │   │   ├── external_resources.yaml     ontology identifiers
        │   │   └── bpod_behavior_columns.yaml  Bpod events, actions and trial columns
        │   ├── adapting_the_pipeline.md    what to edit when the experiment changes
        │   ├── conversion_notes.md         description of the source data and design decisions
        │   └── open_questions.md           questions for the lab, most of them resolved
        ├── interfaces/                 code that reads each data stream
        ├── utils/                      per-session patching of the fiber photometry metadata
        └── tutorials/                  notebooks that read converted files

In NeuroConv, a
[DataInterface](https://neuroconv.readthedocs.io/en/main/user_guide/datainterfaces.html) converts
one data stream to NWB, and an
[NWBConverter](https://neuroconv.readthedocs.io/en/main/user_guide/nwbconverter.html) combines
several interfaces into one file. The interfaces in `interfaces/` are:

| Interface | Reads | Writes |
|---|---|---|
| `DoricFiberPhotometryInterface` (from NeuroConv) | `Session_{session_id}.doric` | Raw fiber photometry series, devices and the fiber photometry table |
| `HanksLabProcessedFiberPhotometryInterface` | `fp_data_{session_id}.pkl` | One processed fiber photometry series |
| `FiberPhotometryArtifactInterface` | `fp_data_{session_id}.pkl` | The `invalid_times` table |
| `BpodBehaviorInterface` | `sess_data_{session_id}.pkl`, `fp_data_{session_id}.pkl` | Bpod task tables and `trials` |
| `SpyglassVideoInterface` | `mov_{session_id}.mp4`, `mov_{session_id}.doric` | Behavior video link and camera |
| `SpyglassEpochInterface` | `mov_{session_id}.doric` | Session epoch and task table |
