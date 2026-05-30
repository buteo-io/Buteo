import importlib
import logging
import os
from fastapi import FastAPI, APIRouter

logger = logging.getLogger(__name__)

def load_plugins(app: FastAPI) -> None:
    """Scan and dynamically load API plugins.
    
    This function discovers python modules and packages inside the current
    directory (api/plugins), imports them, and checks for:
    1. A `register_plugin(app: FastAPI)` function for custom initialization.
    2. A FastAPI `router` variable to automatically mount as an APIRouter.
    """
    plugins_dir = os.path.dirname(__file__)
    
    # Ensure directory exists
    if not os.path.isdir(plugins_dir):
        logger.warning("plugins_directory_missing", extra={"path": plugins_dir})
        return

    logger.info("scanning_plugins", extra={"directory": plugins_dir})
    
    # Iterate through contents of the plugins folder
    for item in os.listdir(plugins_dir):
        # Skip special python directories/files
        if item.startswith("_") or item.startswith("."):
            continue
            
        item_path = os.path.join(plugins_dir, item)
        is_dir = os.path.isdir(item_path)
        is_file = os.path.isfile(item_path) and item.endswith(".py")
        
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
                    register_fn = getattr(module, "register_plugin")
                    register_fn(app)
                    logger.info("plugin_loaded_via_callback", extra={"plugin": plugin_name})
                    
                # Check 2: APIRouter instance
                elif hasattr(module, "router"):
                    router = getattr(module, "router")
                    if isinstance(router, APIRouter):
                        # Mount with automatic prefix /api/plugins/{plugin_name}
                        # if the router doesn't already define its own prefix
                        prefix = f"/api/plugins/{plugin_name}"
                        app.include_router(router, prefix=prefix if not router.prefix else None)
                        logger.info("plugin_router_registered", extra={"plugin": plugin_name, "prefix": prefix})
                    else:
                        logger.warning("plugin_router_invalid_type", extra={"plugin": plugin_name})
                        
            except Exception as e:
                logger.exception("plugin_load_failed", extra={"plugin": plugin_name, "error": str(e)})
