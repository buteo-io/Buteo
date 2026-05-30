"""Uvicorn entry point that disables uvicorn's default log config.

Running via `python run.py` instead of the uvicorn CLI lets us pass
``log_config=None``, which prevents uvicorn from calling dictConfig and
overwriting the structlog handlers that configure_logging() sets up.
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8765")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        log_config=None,
    )
