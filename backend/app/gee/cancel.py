"""Cooperative cancellation for long Earth Engine jobs. Extractors call `check_cancel()` between server round-trips."""
from __future__ import annotations
import threading

_local = threading.local()


class JobCancelled(Exception):
    pass


def set_event(ev: threading.Event | None) -> None:
    _local.event = ev


def check_cancel() -> None:
    ev = getattr(_local, "event", None)
    if ev is not None and ev.is_set():
        raise JobCancelled("cancelled by user")
