"""
export_openapi.py - writes the API's OpenAPI schema to apps/web/openapi.json.

The web app then GENERATES its TypeScript types from it (npm run gen:api), so the
frontend's types always match the backend's Pydantic models. No server needs to run.
"""

import json
import os
from pathlib import Path

os.environ.setdefault("GIGBID_INPROCESS", "1")

from apps.api.main import app

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "web" / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
    print(f"wrote {out}")
