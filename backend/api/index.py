"""AlmaDiet — Vercel serverless entry point.

Vercel's Python runtime imports this module and looks for `app`.
No startup work happens here beyond what main.py already guards:
  * production NEVER runs create_all or seeding (main.py lifespan);
  * migrations run in a controlled release step (`python -m scripts.migrate`),
    never per-request;
  * meal seeding is the explicit admin command (`python -m scripts.seed_meals`).
"""

import os
import sys

# Single path base: the repository root is the Vercel Root Directory, so every
# path in vercel.json is relative to it and this entrypoint is deployed to
# `/var/task/backend/api/index.py`. `main.py` and the `app` package live one
# directory up (`backend/`), so BOTH directories must be importable — resolving
# only this file's own directory made `from main import app` fail with
# ModuleNotFoundError inside the function.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
for _path in (_BACKEND_DIR, _HERE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from main import app  # noqa: E402,F401  (FastAPI ASGI application)

# Serverless note: the lifespan dev-seeding branch is inert here because
# Vercel deploys run with ENVIRONMENT=production (or preview with
# ENVIRONMENT=preview — also treated as non-seeding; see main.py).
