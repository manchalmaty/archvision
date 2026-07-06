"""Retention for the file-based project store (JSON results + IFC exports)."""

import logging
import os
import time

logger = logging.getLogger(__name__)

_MANAGED_SUFFIXES = (".json", ".ifc")


def cleanup_expired_results(directory: str, ttl_days: int) -> int:
    """Delete stored project files older than ttl_days. Returns files removed."""
    if ttl_days <= 0:
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        if not name.endswith(_MANAGED_SUFFIXES):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue  # raced with another delete or unreadable — skip
    if removed:
        logger.info("TTL cleanup removed %d expired project file(s)", removed)
    return removed
