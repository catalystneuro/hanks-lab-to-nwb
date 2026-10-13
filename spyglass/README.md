# Spyglass ingestion for fiber photometry and video

Loads the fiber photometry and the behavior video in the converted Hanks lab NWB files into a local
[Spyglass](https://github.com/LorenFrankLab/spyglass) (DataJoint) database, using the draft
fiber-photometry tables from
[LorenFrankLab/spyglass#1637](https://github.com/LorenFrankLab/spyglass/pull/1637)
(`spyglass.common.common_photometry`). Bpod trials and states and the photometry artifact
intervals stay in the NWB files.

| File | Purpose |
|---|---|
| `docker-compose.yml` | Local MySQL (`spyglass-hanks-db`, host port 3307, named volume) |
| `spyglass-photometry-env.yaml` | Conda env with Spyglass pinned to PR #1637 commit `7a2b9a12b` |
| `check_connection.py` | Checks the database connection and that Spyglass loads |
| `insert_all_sessions.py` | Loads every `.nwb` file in a folder completely: deletes each file's existing entry, registers the session, then inserts photometry and video. Run this after re-converting. |
| `insert_fiber_photometry.py` | Inserts only the photometry tables and their device catalog. |
| `insert_video.py` | Inserts only the video: `CameraDevice`, the epoch (`IntervalList`), `TaskEpoch` (and `Task`) and `VideoFile`. |
| `common.py` | Shared by the loaders: database connection, staging files into the raw dir, and registering the session (`Nwbfile`, `Subject`, `Lab`/`Institution`, `Session`). |
| `tutorials/spyglass_fiber_photometry_tutorial.ipynb` | Tutorial, executed with outputs |

## What ends up in the database

Per session (one converted NWB file):

- `FiberPhotometryConfig`: 8 rows, one per `FiberPhotometryTable` row (4 implant sites ×
  isosbestic/signal excitation), with the indicator, excitation source, photodetector,
  filters, optical fiber, implant region (`BrainRegion`) and fiber insertion coordinates.
- `FiberPhotometryResponseSeries`: 14 rows, one per response series (2 raw ~6 kHz lock-in
  series in `acquisition`, 12 processed ~200 Hz series in `processing/ophys`). Only the NWB
  `object_id` is stored; `fetch1_dataframe()` reads the trace from the file on demand.
- `FiberPhotometryResponseSeries.Fiber`: 4 rows per series, mapping each data column to
  its `FiberPhotometryConfig` row.
- An `IntervalList` entry per series (`"<series name> valid times"`).
- `IntervalList` `"01"`: the session's one epoch, from the NWB `epochs` table.
- `TaskEpoch`: 1 row linking epoch 1 to the task and the camera, from the
  `processing["tasks"]` task table.
- `VideoFile`: 1 row pointing at the `BehaviorVideo` `ImageSeries`. Spyglass only fills
  `VideoFile` for a `TaskEpoch`, which is why the files carry an epoch and a task table.

Shared catalog rows are reused across sessions: the photometry devices (`Indicator`,
`ExcitationSource`, `Photodetector`, `OpticalFilter`, `OpticalFiber`), `CameraDevice`
(`BehaviorCamera`) and `Task` (the Bpod protocol, `ToneCatDelayResp` or `ClassicRLTasks`).

## Setup

1. Start the database from `spyglass/`: `docker compose up -d`.
2. Build the env from the repository root, with any project `.venv` deactivated:

   ```bash
   conda env create -f spyglass/spyglass-photometry-env.yaml
   conda activate spyglass-photometry
   pip install pynwb==4.1.0 hdmf==6.2.0
   ```

   The converted files embed NWB `core` 2.10.0, which needs pynwb 4 and hdmf 6. Spyglass
   depends on `ndx-franklab-novela`, which requires `hdmf<5`, so pip cannot resolve both in
   one step and reports the conflict after the upgrade. Ingestion is not affected because
   Spyglass only imports `ndx-franklab-novela` for type checking. The second step can go
   once `ndx-franklab-novela` supports hdmf 6.

   Spyglass is pinned to a commit on the draft PR branch. Update the pin, and check
   `common.run_table_groups()` against the `single_transaction_make()` signature, when
   LorenFrankLab/spyglass#1637 is merged.
3. Create your own `spyglass/dj_local_conf.json` (below).
4. Check the setup: `python check_connection.py` from `spyglass/` in the
   `spyglass-photometry` env.

### Writing your `dj_local_conf.json`

The file is git-ignored because it holds credentials and machine-specific paths. It is
loaded explicitly by every script here, so it does not interfere with a global
`~/.datajoint_config.json`.

- The password must match `MYSQL_ROOT_PASSWORD` in `docker-compose.yml`.
- Point the `spyglass_dirs` paths at a data folder (`spyglass/spyglass_data/` is
  git-ignored and works fine). NWB files to load go in (or are symlinked into) `raw`.
- Keep `"database.use_tls": false`, which the local Docker MySQL needs.

```json
{
  "database.host": "127.0.0.1",
  "database.port": 3307,
  "database.user": "root",
  "database.password": "<MYSQL_ROOT_PASSWORD from docker-compose.yml>",
  "database.use_tls": false,
  "database.reconnect": true,
  "loglevel": "INFO",
  "safemode": true,
  "fetch_format": "array",
  "enable_python_native_blobs": true,
  "custom": {
    "spyglass_dirs": {
      "base": "<path>/spyglass_data",
      "raw": "<path>/spyglass_data/raw",
      "analysis": "<path>/spyglass_data/analysis",
      "recording": "<path>/spyglass_data/recording",
      "sorting": "<path>/spyglass_data/spikesorting",
      "waveforms": "<path>/spyglass_data/waveforms",
      "temp": "<path>/spyglass_data/tmp",
      "video": "<path>/spyglass_data/video",
      "export": "<path>/spyglass_data/export"
    }
  }
}
```

## Loading sessions

```bash
conda activate spyglass-photometry
cd spyglass
python insert_all_sessions.py ../nwb_output
```

`insert_all_sessions.py` takes a folder and loads every `.nwb` file directly inside it. Each file
is symlinked into the raw dir (the files are ~1.5 GB, so they are not copied). It deletes each file's
previous `Nwbfile` entry first, which removes everything loaded for that session, so it can be
re-run and is the script to use after re-converting.

`insert_fiber_photometry.py` and `insert_video.py` take one or more file paths (or bare file
names already in the raw dir) and insert one
modality. They register the session only if it is missing and skip a session that already has
that modality's rows, so either can be run on its own or added to sessions loaded by the other.
Because they leave a registered file alone, they do not pick up a re-converted file; use
`insert_all_sessions.py` for that.

## Shared tables must match across sessions

`Subject`, `Task`, `CameraDevice` and the photometry device tables (`Indicator`,
`ExcitationSource`, `Photodetector`, `OpticalFilter`, `OpticalFiber`, `DichroicMirror`) are shared by every session in the database
and keyed by name only. If two sessions use the same name with different values, the second
insert stops at an interactive "Existing entry differs in ... Accept the existing value?"
prompt (an `EOFError` when run from a script). The same happens when a device spec is
corrected and the files are re-converted: delete the old catalog row (which cascades to the
sessions that use it) and reload those sessions.

`Subject` has one `age` per subject, while NWB `age` is the age at each session, so the
conversion writes only `date_of_birth` and `Subject.age` stays empty. Age at a session follows
from `date_of_birth` and `session_start_time`.

Device names must therefore mean the same hardware in every session. Excitation filters were
first named by region, and the region-to-channel patching changes
between sessions, so the same name referred to different filters and the second session failed
to load. They are now named per Doric channel (`excitation_filter_isosbestic_AIN01`), like the
photodetectors. Details are in *Excitation filter naming* in
[`conversion_notes.md`](../src/hanks_lab_to_nwb/embargo2026/conversion_notes.md). Files
converted before 2026-09-29 carry the old names and need re-converting before loading more
than one into the same database.

## Video files

`VideoFile` stores the `ImageSeries` object ID, and the video can be read through it:
`(VideoFile & key).fetch_nwb()[0]["video_file"].external_file`. Spyglass's own path lookup,
`VideoFile.get_abs_path()`, only finds a video copied into the Spyglass `video` directory under
the `ImageSeries` name. It is used only by Spyglass's DeepLabCut pipeline and is not set up
here, because every session's series is named `BehaviorVideo`.

The camera's `lens` and `meters_per_pixel` are placeholders (`unknown`, `0.0`) until the lab
confirms them (see `open_questions.md`).

## Why not `sgi.insert_sessions()`?

`insert_sessions()` always runs `populate_all_common()`, which tries every common table
(ephys, position, video, optogenetics, ...) and imports the spike-sorting/decoding
modules. Most of that does not apply to this dataset. The loader instead runs Spyglass's own
`single_transaction_make()` over only the photometry and video tables and their parents, so
nothing unrelated is attempted.
