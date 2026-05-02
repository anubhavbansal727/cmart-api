from __future__ import annotations

import time
from types import TracebackType


class StageTimer:
    """Context manager that measures elapsed wall-clock time for a pipeline stage.

    Usage::

        with StageTimer() as t:
            await some_pipeline_stage()

        print(t.elapsed_ms)  # float — milliseconds
    """

    def __init__(self) -> None:
        self._start_ns: int = 0
        self._end_ns: int = 0

    def __enter__(self) -> StageTimer:
        self._start_ns = time.perf_counter_ns()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._end_ns = time.perf_counter_ns()

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds. Valid only after __exit__ has been called."""
        if self._end_ns == 0:
            # Timer still running — return live reading
            return (time.perf_counter_ns() - self._start_ns) / 1_000_000
        return (self._end_ns - self._start_ns) / 1_000_000

    @property
    def elapsed_ms_int(self) -> int:
        """Elapsed time rounded to the nearest millisecond."""
        return round(self.elapsed_ms)
