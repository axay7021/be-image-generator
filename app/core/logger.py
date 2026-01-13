import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(levelname)s %(asctime)s - %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3
ENCODING = "utf-8"

# Define Log Files
APP_LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "error.log"
REQUEST_LOG_FILE = LOG_DIR / "request.log"

# --- Formatters ---
formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)


# --- Helper Functions ---
def get_console_handler() -> logging.StreamHandler:
    """Returns a configured console handler."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    return console_handler


def get_file_handler(
    filename: Path, level: int = logging.INFO, backup_count: int = BACKUP_COUNT
) -> RotatingFileHandler:
    """Returns a configured rotating file handler."""
    file_handler = RotatingFileHandler(
        filename, maxBytes=MAX_BYTES, backupCount=backup_count, encoding=ENCODING
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    return file_handler


# --- Logger Setup ---

# 1. Main Application Logger
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

if not logger.hasHandlers():
    # File Handler for general logs
    app_file_handler = get_file_handler(APP_LOG_FILE)
    logger.addHandler(app_file_handler)

    # File Handler for error logs
    error_file_handler = get_file_handler(ERROR_LOG_FILE, level=logging.ERROR)
    logger.addHandler(error_file_handler)


# 2. Request Logger (Isolated)
request_logger = logging.getLogger("request")
request_logger.setLevel(logging.INFO)
request_logger.propagate = False  # Prevent propagation to root logger

if not request_logger.hasHandlers():
    request_file_handler = get_file_handler(REQUEST_LOG_FILE, backup_count=5)
    request_logger.addHandler(request_file_handler)


# 3. Root Logger Configuration
# Configure root logger to capture logs from libraries, but prevent hijacking by others
root_logger = logging.getLogger()
if not root_logger.hasHandlers():
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(get_console_handler())


# 4. External Library Log Suppression
# Suppress noisy loggers from external libraries
NOISY_LOGGERS = ["mcp", "fastmcp", "livekit.agents.mcp", "httpcore", "httpx"]
for logger_name in NOISY_LOGGERS:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# Configure Uvicorn Loggers
# Explicitly configure uvicorn loggers to use our format
UVICORN_LOGGERS = ["uvicorn", "uvicorn.error", "uvicorn.access"]
for logger_name in UVICORN_LOGGERS:
    # Use a different variable name to avoid shadowing 'logger' from outer scope
    uvicorn_logger = logging.getLogger(logger_name)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(get_console_handler())
    uvicorn_logger.setLevel(logging.INFO)
    uvicorn_logger.propagate = False  # Prevent double logging since we added a handler
