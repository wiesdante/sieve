"""Run blocking work off the UI thread and get results back as Qt signals."""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)

_running: set[BackgroundTask] = set()


class BackgroundTask(QObject):
    succeeded = Signal(object)
    failed = Signal(object)
    progress = Signal(object, object)
    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()


class _Runnable(QRunnable):
    def __init__(self, task: BackgroundTask, fn: Callable[..., Any], args, kwargs) -> None:
        super().__init__()
        self._task, self._fn, self._args, self._kwargs = task, fn, args, kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:
            log.debug("Background task failed", exc_info=True)
            self._task.failed.emit(exc)
        else:
            self._task.succeeded.emit(result)
        finally:
            self._task.finished.emit()


def run_in_background(
    fn: Callable[..., Any],
    *args: Any,
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    on_progress: Callable[[Any, Any], None] | None = None,
    **kwargs: Any,
) -> BackgroundTask:
    """Run ``fn`` on the thread pool.

    If ``fn`` accepts ``progress`` or ``cancelled`` keyword arguments they are
    supplied automatically; callbacks are always invoked on the UI thread.
    """
    task = BackgroundTask()
    params = inspect.signature(fn).parameters
    if "progress" in params:
        kwargs.setdefault("progress", lambda done, total: task.progress.emit(done, total))
    if "cancelled" in params:
        kwargs.setdefault("cancelled", task.is_cancelled)

    if on_success:
        task.succeeded.connect(on_success)
    if on_error:
        task.failed.connect(on_error)
    if on_progress:
        task.progress.connect(on_progress)

    _running.add(task)
    task.finished.connect(lambda: _running.discard(task))
    QThreadPool.globalInstance().start(_Runnable(task, fn, args, kwargs))
    return task
