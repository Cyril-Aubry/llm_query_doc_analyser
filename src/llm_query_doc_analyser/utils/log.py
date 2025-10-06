# utils/log.py
import logging
from datetime import datetime
from pathlib import Path
from typing import cast

import structlog


def setup_logging(session_id: str | None = None, log_level: str = "INFO", console_output: bool = True) -> Path:
    """
    Configure structured logging to file (JSONL) and optionally to console (pretty).
    
    Args:
        session_id: Session identifier for log file naming
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Whether to output logs to console (default: True)
    
    Returns:
        The session log file Path.
    """
    # --- paths ---
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"session_{session_id}.jsonl"

    # --- stdlib logging baseline ---
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.root.handlers.clear()
    logging.root.setLevel(level)

    # Shared processors (NO final renderer here — ProcessorFormatter will add it)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Console (human-readable) - optional
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # Formatter for console (pretty)
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(),  # pretty console
            ]
        )
        console_handler.setFormatter(console_formatter)
        logging.root.addHandler(console_handler)

    # File (JSON lines) - always enabled
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(level)
    
    # Formatter for file (JSON)
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),  # JSON lines in file
        ]
    )
    file_handler.setFormatter(json_formatter)
    logging.root.addHandler(file_handler)

    # --- structlog config ---
    structlog.configure(
        processors=[
            # Keep these lightweight because ProcessorFormatter will run the rest
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),  # go through stdlib logging
        cache_logger_on_first_use=True,
    )

    return log_file

def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound logger for a module/package."""
    # add_logger_name processor already injects the name; no need to bind a duplicate field
    return cast(structlog.BoundLogger, structlog.get_logger(name))
    return structlog.get_logger(name)
