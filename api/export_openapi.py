"""Write the API's OpenAPI description to web/openapi.json.

The web app generates its TypeScript types from that file (`npm run gen:api` in web/), so the screens and the
API can't silently drift apart. Run from the repo root after changing any endpoint or response shape:

    python -m api.export_openapi
"""
import json
from pathlib import Path

from .app import app

OUT = Path(__file__).resolve().parent.parent / "web" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT}")
