"""Qt signal bus that bridges background threads to the UI.

Workers don't know about Qt - they call plain callables. We funnel those
through a QObject that emits signals on the main thread.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject, Signal  # noqa: F401


def make_bus():  # type: ignore[no-untyped-def]
    """Create the signal bus lazily so this module is importable without Qt."""
    from PySide6.QtCore import QObject, Signal

    class SignalBus(QObject):
        progress = Signal(int, dict)
        status_changed = Signal(int, str, str)
        queue_changed = Signal()
        installer_progress = Signal(float, str)
        toast = Signal(str, str)  # level, message

    return SignalBus()
