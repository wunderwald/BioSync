import os
from pathlib import Path

# Must be set before anything imports pyplot, so tests never open a window.
os.environ["MPLBACKEND"] = "Agg"

import pytest

import xlsx
from signal_processing import preprocess_dyad

SIMULATED_DYADS = Path(__file__).parents[1] / "simulated_data" / "dyads_simulated"


@pytest.fixture
def load_simulated_dyad():
    """Returns a function that runs a simulated dyad through file reading and preprocessing."""
    def _load(name):
        columns = [
            xlsx.get_columns(xlsx.read_xlsx(SIMULATED_DYADS / name / file), "IBI Series")["IBI_ms"]
            for file in ("HRV_A.xlsx", "HRV_B.xlsx")
        ]
        signal_a, signal_b, _, _ = preprocess_dyad(columns[0], columns[1], signal_type="event-based")
        return signal_a, signal_b
    return _load
