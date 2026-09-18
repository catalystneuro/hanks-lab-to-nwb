"""Interface for a single processed fiber photometry signal from fp_data_*.pkl."""

import pickle
from pathlib import Path

import numpy as np
from neuroconv.datainterfaces.fiber_photometry.basefiberphotometryinterface import (
    BaseFiberPhotometryInterface,
)


class HanksLabProcessedFiberPhotometryInterface(BaseFiberPhotometryInterface):
    """Read one decimated processed FP signal from fp_data_*.pkl.

    Instantiate once per signal type (raw_iso, dff_iso, etc.), configured via
    signal_key and metadata_key. The base class handles FP table construction and
    timing; this class adds only the pkl-reading seam.
    """

    keywords = ["fiber photometry", "dopamine", "dLight", "dFF"]

    def __init__(self, file_path: Path | str, ain_to_region: dict, signal_key: str, metadata_key: str):
        """
        Parameters
        ----------
        file_path :
            Path to the processed FP pickle (fp_data_{sessid}.pkl).
        ain_to_region :
            Mapping of AIN channel numbers to brain region names,
            e.g. {1: "NAc", 2: "PL", 3: "DLS", 4: "DMS"}.
        signal_key :
            Key in fp_data["fp_data"]["processed_signals"][region] to read,
            e.g. "dff_iso", "raw_iso", "raw_lig", "filtered_iso", etc.
        metadata_key :
            Key under metadata["FiberPhotometry"] for this series,
            e.g. "dff_series", "raw_iso_series", etc.
        """
        self.ain_to_region = ain_to_region
        self.signal_key = signal_key
        stream_names = [f"sig_ain0{ain}" for ain in sorted(ain_to_region)]
        super().__init__(
            stream_names=stream_names,
            metadata_key=metadata_key,
            fp_data_file_path=file_path,
        )
        with open(file_path, "rb") as f:
            self.fp_data = pickle.load(f)

    # ── Format-reading seam ────────────────────────────────────────────────

    def _get_stream_data(self, *, stream_name: str) -> np.ndarray:
        ain = int(stream_name[-1])
        region = self.ain_to_region[ain]
        return np.asarray(self.fp_data["fp_data"]["processed_signals"][region][self.signal_key])

    def _get_stream_timestamps(self, *, stream_name: str) -> np.ndarray:
        return np.asarray(self.fp_data["fp_data"]["time"])
