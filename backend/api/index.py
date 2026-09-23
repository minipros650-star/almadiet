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

# Ensure `backend` is importable regardless of the invocation cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app  # noqa: E402,F401  (FastAPI ASGI application)

# Serverless note: the lifespan dev-seeding branch is inert here because
# Vercel deploys run with ENVIRONMENT=production (or preview with
# ENVIRONMENT=preview — also treated as non-seeding; see main.py).
