"""Settings from the environment and business constants.

Environment settings have defaults, so the app starts without any .env file.
Business constants live here (not in env): they do not differ between environments.
"""

import os
from datetime import time, timedelta
from zoneinfo import ZoneInfo

# --- Environment -------------------------------------------------------------

DEFAULT_DATABASE_PATH = "./data/crm.db"
PORT = int(os.environ.get("PORT", "8000"))

# How long a request waits for the SQLite write lock before answering 503.
DB_BUSY_TIMEOUT_SECONDS = 5.0


def database_path() -> str:
    """Read lazily so tests and scripts can set DATABASE_PATH before app creation."""
    return os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)


# --- Business rules ----------------------------------------------------------

MEETING_DURATION = timedelta(minutes=60)

# Working hours are checked in Almaty local time. The UTC offset is NOT hardcoded:
# Kazakhstan moved from UTC+6 to UTC+5 in 2024, and the tz database knows that.
BUSINESS_TZ = ZoneInfo("Asia/Almaty")
WORKDAY_START = time(9, 0)
WORKDAY_END = time(18, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday..Friday (datetime.weekday())

# --- Pagination --------------------------------------------------------------

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
