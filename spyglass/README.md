# Spyglass ingestion for fiber photometry

Loads the fiber photometry in the converted Hanks lab NWB files into a local
[Spyglass](https://github.com/LorenFrankLab/spyglass) (DataJoint) database, using the draft
fiber-photometry tables from
[LorenFrankLab/spyglass#1637](https://github.com/LorenFrankLab/spyglass/pull/1637)
(`spyglass.common.common_photometry`).

| File | Purpose |
|---|---|
| `docker-compose.yml` | Local MySQL (`spyglass-hanks-db`, host port 3307, named volume) |
| `spyglass-photometry-env.yaml` | Conda env with Spyglass pinned to PR #1637 commit `7a2b9a12b` |
| `check_connection.py` | Checks the database connection and that Spyglass loads |
| `insert_fiber_photometry.py` | The loader. Fills only the photometry tables and the parents they require (`Session`, `Subject`, `Lab`/`Institution`, device catalog). |
| `notebooks/spyglass_fiber_photometry_tutorial.ipynb` | Tutorial, executed with outputs |

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

Shared device catalog (`Indicator`, `ExcitationSource`, `Photodetector`, `OpticalFilter`,
`OpticalFiber`) rows are reused across sessions.

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
   `insert_fiber_photometry.py` against the `single_transaction_make()` signature, when
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
python insert_fiber_photometry.py ../nwb_output/*.nwb
```

A path outside the raw dir is symlinked into it (the files are ~1.5 GB, so they are not
copied); a bare file name is expected to already be there. Re-running a file deletes its
previous `Nwbfile` entry first, so the script is idempotent.

## Shared tables must match across sessions

`Subject` and the device tables (`Indicator`, `ExcitationSource`, `Photodetector`,
`OpticalFilter`, `OpticalFiber`, `DichroicMirror`) are shared by every session in the database
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

## Why not `sgi.insert_sessions()`?

`insert_sessions()` always runs `populate_all_common()`, which tries every common table
(ephys, position, video, optogenetics, ...) and imports the spike-sorting/decoding
modules. None of that applies to this dataset. The loader instead runs Spyglass's own
`single_transaction_make()` over only the photometry tables and their parents, so nothing
unrelated is attempted.
