"""Start the API: python -m api  (http://127.0.0.1:8000, interactive docs at /docs)."""
import uvicorn

from data.db import get_setting

if __name__ == "__main__":
    # Bound to this computer only: there is no login yet.
    uvicorn.run("api.app:app", host="127.0.0.1", port=int(get_setting("API_PORT") or 8000))
