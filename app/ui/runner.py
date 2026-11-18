"""Background diagnosis worker.

The diagnostic engine is blocking, so it always runs on a dedicated
``QThread``. Results are forwarded to the GUI thread through Qt signals, which
is what keeps the interface responsive and cancellable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.core.engine import DiagnosticEngine
from app.core.models import ChangeRecord, DiagnosticReport
from app.core.settings import AppSettings


class DiagnosisWorker(QThread):
    """Runs :class:`DiagnosticEngine` off the GUI thread."""

    #: percent complete, human readable task name
    progressed = Signal(int, str)
    #: section name ("gateway", "internet", "dns", ...), payload object
    section_ready = Signal(str, object)
    #: final report
    completed = Signal(object)
    #: unexpected failure message
    failed = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        applied_changes: list[ChangeRecord] | None = None,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = DiagnosticEngine(
            settings,
            applied_changes=list(applied_changes or []),
        )

    # ------------------------------------------------------------------ #

    def run(self) -> None:  # noqa: D102 - Qt entry point
        try:
            report: DiagnosticReport = self._engine.run(
                on_progress=self._on_progress,
                on_result=self._on_result,
            )
        except Exception as exc:  # noqa: BLE001 - never let a thread die silently
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.completed.emit(report)

    def _on_progress(self, percent: int, task: str | None) -> None:
        self.progressed.emit(int(percent), str(task or ""))

    def _on_result(self, name: str, payload: Any) -> None:
        self.section_ready.emit(name, payload)

    # ------------------------------------------------------------------ #

    def cancel(self) -> None:
        """Ask the engine to stop as soon as the current probe finishes."""
        self._engine.cancel()


class CallableWorker(QThread):
    """Runs a blocking callable off the GUI thread and reports its result.

    Used by the settings page so that reading Windows network settings, applying
    a change or restoring a snapshot never freezes the interface.
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        function: Callable[..., Any],
        *args: Any,
        parent: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self._function = function
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:  # noqa: D102 - Qt entry point
        try:
            result = self._function(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.succeeded.emit(result)


__all__ = ["CallableWorker", "DiagnosisWorker"]
