"""Task-local progress hook; safe to import without the optional A2A SDK."""
from contextvars import ContextVar

_progress_callback = ContextVar('framework_a2a_progress', default=None)


async def report_progress(event: str, payload: dict | None = None):
    callback = _progress_callback.get()
    if callback is not None:
        await callback(event, payload or {})
