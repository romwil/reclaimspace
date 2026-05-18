"""Run the Reclaimspace web UI."""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8777"))
    uvicorn.run(
        "reclaimspace.web.app:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
