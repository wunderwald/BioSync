import os
from pathlib import Path

# Must be set before anything imports pyplot, so tests never open a window.
os.environ["MPLBACKEND"] = "Agg"

import pytest

import state
import xlsx
from signal_processing import preprocess_dyad

SIMULATED_DYADS = Path(__file__).parents[1] / "simulated_data" / "dyads_simulated"


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.fixture
def fake_state(monkeypatch):
    """Replaces every tk.Var in state, so GUI logic can run without a window."""
    for name in vars(state).copy():
        if name.startswith("val_"):
            monkeypatch.setattr(state, name, FakeVar(""), raising=True)
    return state


@pytest.fixture
def opened_workbooks(monkeypatch):
    """Records the workbooks that xlsx.py opens, so that a test can check they were closed."""
    workbooks = []
    real_load = xlsx.load_workbook

    def recording_load(*args, **kwargs):
        workbooks.append(real_load(*args, **kwargs))
        return workbooks[-1]

    monkeypatch.setattr(xlsx, "load_workbook", recording_load)
    return workbooks


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
