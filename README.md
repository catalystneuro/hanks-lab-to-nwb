# hanks-lab-to-nwb
NWB conversion scripts for Hanks lab data to the
[Neurodata Without Borders](https://nwb-overview.readthedocs.io/) data format.


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

### Running a conversion

Run the scripts through uv so they use the project environment:

```bash
uv run python src/hanks_lab_to_nwb/embargo2026/convert_session.py
uv run python src/hanks_lab_to_nwb/embargo2026/convert_all_sessions.py <data_dir_path> <output_dir_path>
```

## Helpful Definitions

This conversion project is comprised primarily by DataInterfaces, NWBConverters, and conversion scripts.

In neuroconv, a [DataInterface](https://neuroconv.readthedocs.io/en/main/user_guide/datainterfaces.html) is a class that specifies the procedure to convert a single data modality to NWB.
This is usually accomplished with a single read operation from a distinct set of files.
For example, in this conversion, the `HanksTaskBehaviorInterface` contains the code that converts all of the behavioral data to NWB from raw <FILE_TYPE> files.

In neuroconv, a [NWBConverter](https://neuroconv.readthedocs.io/en/main/user_guide/nwbconverter.html) is a class that combines many data interfaces and specifies the relationships between them, such as temporal alignment.
This allows users to combine multiple modalities into a single NWB file in an efficient and modular way.

In this conversion project, the conversion scripts determine which sessions to convert,
instantiate the appropriate NWBConverter object,
and convert all of the specified sessions, saving them to an output directory of .nwb files.


## Repository structure
Each conversion is organized in a directory of its own in the `src` directory:

    hanks-lab-to-nwb/
    ├── LICENSE
    ├── pyproject.toml
    ├── README.md
    └── src
        ├── hanks_lab_to_nwb
        │   └── hanks_task
        │       ├── conversion_notes.md
        │       ├── behaviorinterface.py
        │       ├── convert_session.py
        │       ├── metadata.yml
        │       ├── nwbconverter.py
        │       └── __init__.py
        │   ├── conversion_directory_b

        └── __init__.py

For example, for the conversion `hanks_task` you can find a directory located in `src/hanks-lab-to-nwb/hanks_task`.
Inside each conversion directory you can find the following files:


* `convert_sesion.py`: this script defines the function to convert one full session of the conversion.
* `metadata.yml`: metadata in yaml format for this specific conversion.
* `behaviorinterface.py`: the behavior interface. Usually ad-hoc for each conversion.
* `nwbconverter.py`: the place where the `NWBConverter` class is defined.
* `conversion_notes.md`: notes and comments concerning this specific conversion.

The directory might contain other files that are necessary for the conversion but those are the central ones.


## Data Conversion Pipeline

This project implements a comprehensive pipeline for converting electrophysiology and behavioral data to NWB format:

**Source Data → Data Interfaces → NWB Files**

## Customizing for New Datasets
To create a new conversion:
1. **Create a new dataset directory** following the naming convention `{experimenter}_{year}`
2. **Implement dataset-specific interfaces** inheriting from existing interfaces as appropriate
3. **Create an NWBConverter class** that combines all interfaces for your dataset
4. **Write conversion scripts** for single sessions and batch processing
6. **Create metadata files** with dataset-specific experimental parameters
Each conversion should be self-contained within its directory and follow the established patterns for consistency and maintainability.
