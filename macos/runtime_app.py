"""macOS-only entry point and instance identity for safe launcher health checks."""

import os
from neveai.main import app


@app.get("/health/macos", include_in_schema=False)
async def macos_health():
    return {"instance": os.environ.get("NEVE_MACOS_INSTANCE", "")}
