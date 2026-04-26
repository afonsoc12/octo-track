"""Logging configuration for octopus-api-consumer.

Optimized for Docker/container environments with support for structured logging.
"""

import logging
import logging.handlers
import os
import sys


class LogfmtFormatter(logging.Formatter):
    """Format logs in logfmt style for easy machine parsing.

    Logfmt is a simple text-based format for structured logging.
    Example: time=2026-02-11T20:00:00Z level=INFO logger=octopus.py msg="Starting sync"
    """

    def format(self, record):
        """Format a log record as logfmt."""
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ")
        level = record.levelname.lower()
        logger_name = record.name.split(".")[-1]  # Use just the module name
        msg = record.getMessage()

        # Escape quotes in message
        msg = msg.replace('"', '\\"')

        # Base logfmt output
        logfmt_parts = [
            f"time={timestamp}",
            f"level={level}",
            f"logger={logger_name}",
            f'msg="{msg}"',
        ]

        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info).replace("\n", "\\n")
            logfmt_parts.append(f'exc="{exc_text}"')

        return " ".join(logfmt_parts)


def setup_logging(log_level=None, use_logfmt=None):
    """Set up logging for the application.

    Optimized for Docker/container environments. Logs to stdout/stderr by default.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
                  If None, uses LOG_LEVEL env var or defaults to INFO.
        use_logfmt: Use logfmt structured format.
                   If None, uses LOG_FORMAT env var. Defaults to False.
    """
    # Get log level from argument, environment variable, or default
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "info").upper()

    # Validate log level
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")

    # Determine log format
    if use_logfmt is None:
        log_format = os.getenv("LOG_FORMAT", "text").lower()
        use_logfmt = log_format == "logfmt"

    # Create logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatter based on format choice
    if use_logfmt:
        formatter = LogfmtFormatter()
    else:
        # Simple text formatter for console (optimal for Docker/human readable)
        formatter = logging.Formatter(
            fmt="%(levelname)-8s | %(name)s | %(message)s",
        )

    # Console handler - log to stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set third-party library log levels to WARNING to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("psycopg").setLevel(logging.WARNING)

    return root_logger


def get_logger(name):
    """Get a logger instance for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        logging.Logger instance
    """
    return logging.getLogger(name)
