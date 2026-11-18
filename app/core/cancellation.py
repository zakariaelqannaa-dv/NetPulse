"""Cancellation primitives shared by the diagnostic engine and the GUI."""

from __future__ import annotations

import threading


class OperationCancelled(Exception):
    """Raised when a cancellable operation is stopped by the user."""


class CancellationToken:
    """A thread-safe cancellation flag.

    A single token is handed to every diagnostic worker so that pressing Stop
    in the GUI stops long running probes (ping loops, tracert, DNS) quickly.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation. Safe to call from any thread."""
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """Sleep for ``timeout`` seconds, waking early when cancelled.

        Returns ``True`` when cancellation was requested.
        """
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise OperationCancelled("Operation cancelled by user")
