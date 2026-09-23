"""AlmaDiet — Structured logging.

Rule: health values, allergy lists, tokens and passwords never enter logs
(see docs/PRIVACY_AND_DATA.md §2). Services log ids and event codes only.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    )
    root = logging.getLogger("almadiet")
    root.setLevel(level)
    root.handlers = [handler]
    root.propagate = False

    # Quiet third-party noise.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
