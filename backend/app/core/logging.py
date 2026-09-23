"""
AlmaDiet — Structured logging.

Rule: health values, allergy lists, and plan contents NEVER enter logs.
Log lines carry event codes and identifiers only (see docs/PRIVACY_AND_DATA.md).
"""

from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Quiet down noisy libraries in production
    if not debug:
        for noisy in ("uvicorn.access", "sqlalchemy.engine"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
