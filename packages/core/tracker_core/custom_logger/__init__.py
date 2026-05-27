"""Configure logging."""

import contextlib
import logging
import os
import sys
import traceback
from typing import Any

import structlog

shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def _extra_event_dict_processing(_, __, event_dict: dict[Any, Any]) -> dict[Any, Any]:
    with contextlib.suppress(KeyError):
        del event_dict["color_message"]
    return event_dict


def _short_path(path: str) -> str:
    norm = path.replace("\\", "/")
    parts = norm.split("/")
    if "trackmy-core" in parts:
        idx = parts.index("trackmy-core")
        return "/".join(parts[idx + 1 :])
    if "app" in parts:
        idx = parts.index("app")
        return "/".join(parts[idx + 1 :])
    return "/".join(parts[-4:])


def _compact_exc_info(_, __, event_dict: dict[Any, Any]) -> dict[Any, Any]:
    exc_info = event_dict.get("exc_info")
    if not exc_info:
        return event_dict

    if exc_info is True:
        exc_info = sys.exc_info()
    elif isinstance(exc_info, BaseException):
        exc_info = (type(exc_info), exc_info, exc_info.__traceback__)

    if not isinstance(exc_info, tuple) or len(exc_info) != 3:
        return event_dict

    exc_type, exc, tb = exc_info
    frames = traceback.extract_tb(tb) if tb else []
    frame = next((f for f in reversed(frames) if "site-packages" not in f.filename), None)
    if frame is None and frames:
        frame = frames[-1]

    event_dict["error_type"] = exc_type.__name__ if exc_type else type(exc).__name__
    event_dict["error"] = str(exc) if exc else ""
    if frame:
        event_dict["error_at"] = f"{_short_path(frame.filename)}:{frame.lineno} ({frame.name})"

    event_dict.pop("exc_info", None)
    event_dict.pop("exception", None)
    return event_dict


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_logging(level: str | None = None, debug: bool = False) -> None:
    """Configure the logging for kelvin green stack.

    Parameters
    ----------
    level : str
        The logging level to set for the root logger.
    debug : bool
        Whether to enable debug mode with colored console output.

    """
    effective_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    compact_exceptions = _env_bool("COMPACT_EXCEPTIONS", default=True)
    dev_logs = debug or _env_bool("DEV_LOGS", default=False) or _env_bool("COLOR_LOGS", default=False)

    structlog.stdlib.recreate_defaults()

    if dev_logs:
        extra_processors = [structlog.dev.ConsoleRenderer(colors=True)]
    else:
        exception_processor = _compact_exc_info if compact_exceptions else structlog.processors.dict_tracebacks
        extra_processors = [
            exception_processor,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ExtraAdder(),
            _extra_event_dict_processing,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *extra_processors,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(effective_level)

    for name in [
        "gunicorn",
        "gunicorn.error",
        "gunicorn.access",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ]:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = False
