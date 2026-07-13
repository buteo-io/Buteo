"""Dynamic plugin loader for optional API extensions."""

import importlib
import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI

logger = logging.getLogger(__name__)


def load_plugins(app: FastAPI) -> None:
    """Scan and dynamically load API plugins.

    This function discovers python modules and packages inside the current
    directory (api/plugins), imports them, and checks for:
    1. A `register_plugin(app: FastAPI)` function for custom initialization.
    2. A FastAPI `router` variable to automatically mount as an APIRouter.
    """
    plugins_dir = Path(__file__).parent

    # Ensure directory exists
    if not plugins_dir.is_dir():
        logger.warning("plugins_directory_missing", extra={"path": str(plugins_dir)})
        return

    logger.info("scanning_plugins", extra={"directory": str(plugins_dir)})

    # Iterate through contents of the plugins folder
    for item_path in plugins_dir.iterdir():
        item = item_path.name
        # Skip special python directories/files
        if item.startswith(("_", ".")):
            continue

        is_dir = item_path.is_dir()
        is_file = item_path.is_file() and item.endswith(".py")

        if is_dir or is_file:
            plugin_name = item[:-3] if is_file else item

            try:
                # Import module dynamically relative to this package
                # Since api/main.py imports this, our absolute module path
                # will be api.plugins.<plugin_name>
                module_path = f"api.plugins.{plugin_name}"
                module = importlib.import_module(module_path)

                # Check 1: Custom registration function
                if hasattr(module, "register_plugin"):
                    register_fn = module.register_plugin
                    register_fn(app)
                    logger.info("plugin_loaded_via_callback", extra={"plugin": plugin_name})

                # Check 2: APIRouter instance
                elif hasattr(module, "router"):
                    router = module.router
                    if isinstance(router, APIRouter):
                        # Mount with automatic prefix /api/plugins/{plugin_name}
                        # if the router doesn't already define its own prefix
                        prefix = f"/api/plugins/{plugin_name}"
                        app.include_router(router, prefix=prefix if not router.prefix else None)
                        logger.info(
                            "plugin_router_registered",
                            extra={"plugin": plugin_name, "prefix": prefix},
                        )
                    else:
                        logger.warning("plugin_router_invalid_type", extra={"plugin": plugin_name})

            except Exception as e:
                logger.exception("plugin_load_failed", extra={"plugin": plugin_name, "error": str(e)})
