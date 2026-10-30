"""Protocol that every mode controller satisfies."""
from typing import Protocol, runtime_checkable

from core.sweep_state import SweepState


@runtime_checkable
class MeasurementMode(Protocol):
    state: SweepState

    def set_output_dir(self, path: str) -> None:
        ...

    def run_measurement(self) -> None:
        ...

    def abort_measurement(self) -> None:
        ...
