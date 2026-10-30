"""Observable run state (progress, results, faults) for one mode."""
from atom.api import Atom, Bool, ContainerList, Dict, Int, Str


class SweepState(Atom):
    running = Bool(False)

    active_pixel = Str("--")
    progress_percent = Int(0)
    progress_text = Str("")

    log_lines = ContainerList(str)
    results = ContainerList(Dict())
    faults = ContainerList(Dict())

    finished_aborted = Bool(False)
    finished_had_error = Bool(False)
    finish_count = Int(0)
