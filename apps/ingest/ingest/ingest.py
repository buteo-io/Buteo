"""Start all ingest servers: Codec 8 TCP + OsmAnd HTTP.

Run with:
    python -m ingest.ingest
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from tracker_core.custom_logger import configure_logging
from tracker_core.internal.appctx.config import AppConfig

from .codec8.codec8 import serve as serve_codec8
from .osmand.api import app as osmand_app

logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting ingest servers")
    osmand = uvicorn.Server(
        uvicorn.Config(
            osmand_app,
            host=AppConfig.ingest_host,
            port=AppConfig.ingest_osmand_port,
            proxy_headers=True,
            forwarded_allow_ips="*",
            access_log=False,
            log_config=None,
        ),
    )
    logger.info("listening for osmand", extra={"port": AppConfig.ingest_osmand_port})
    logger.info("listening for codec8", extra={"port": AppConfig.ingest_codec8_port})
    await asyncio.gather(serve_codec8(), osmand.serve())


if __name__ == "__main__":
    configure_logging(AppConfig.log_level, debug=AppConfig.debug)
    asyncio.run(main())
