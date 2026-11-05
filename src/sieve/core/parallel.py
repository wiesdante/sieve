"""Run jobs on a few threads, without ever letting one stuck job stall the run.

Jobs run on daemon threads: a job stuck in a network call can be given up (after
``hard_limit`` seconds) or left behind when the run is stopped, and it can never
keep the app from closing.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence

log = logging.getLogger(__name__)

#: After Stop, running jobs get this long to finish before the run ends without them.
STOP_GRACE = 5.0


def run_parallel[T, R](
    items: Sequence[T],
    work: Callable[[int, T], R],
    workers: int,
    on_result: Callable[[int, R], None],
    cancelled: Callable[[], bool] | None = None,
    hard_limit: float | None = None,
    give_up: Callable[[int, T, float], R] | None = None,
    on_error: Callable[[int, T, Exception], R] | None = None,
    stop_grace: float | None = None,
) -> bool:
    """Run ``work(index, item)`` for every item, ``workers`` at a time.

    ``on_result`` is called on the calling thread, in completion order. A job still
    running after ``hard_limit`` seconds is reported with ``give_up(index, item,
    seconds)``. Returns True if the run was stopped through ``cancelled``.
    """
    workers = max(1, min(workers, len(items) or 1))
    grace = STOP_GRACE if stop_grace is None else stop_grace
    pending = deque(enumerate(items))
    finished: queue.Queue[tuple[int, R]] = queue.Queue()
    running: dict[int, tuple[T, float]] = {}
    stop_deadline: float | None = None
    stopped = False

    def start(index: int, item: T) -> None:
        def job() -> None:
            try:
                result = work(index, item)
            except Exception as exc:  # a bug in one job must not end the run
                log.exception("Job %s failed", index)
                if on_error is None:
                    return
                result = on_error(index, item, exc)
            finished.put((index, result))

        running[index] = (item, time.monotonic())
        threading.Thread(target=job, name=f"job-{index}", daemon=True).start()

    def fill() -> None:
        while pending and len(running) < workers:
            start(*pending.popleft())

    fill()
    while running:
        try:
            index, result = finished.get(timeout=0.25)
        except queue.Empty:
            pass
        else:
            if running.pop(index, None) is not None:
                on_result(index, result)
        now = time.monotonic()
        if hard_limit is not None:
            for index, (item, started) in list(running.items()):
                if now - started > hard_limit:
                    del running[index]
                    if give_up is not None:
                        on_result(index, give_up(index, item, now - started))
        if cancelled and cancelled():
            stopped = True
            pending.clear()
            if stop_deadline is None:
                stop_deadline = now + grace
            elif now > stop_deadline:
                break  # jobs still running are left behind; their threads end on their own
        fill()
    return stopped
