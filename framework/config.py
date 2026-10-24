"""Runtime configuration for the suite (all overridable through environment variables)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency). Real environment variables win over the file."""
    for env_file in (ROOT / ".env", Path.cwd() / ".env"):
        if not env_file.is_file():
            continue
        for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip("\"'")
            if key and value:                       # empty values are ignored
                os.environ.setdefault(key, value)


_load_dotenv()

# --- how to reach the application -------------------------------------------------
# BASE_URL          use an already running instance (no DB/filesystem access, tests that
#                   need it are skipped). Never point this at production data.
# RAPID_TASK_SRC    path to the application project (contains app/ and static/). The suite
#                   copies it into a temp dir and starts its own isolated instance there.
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
APP_SRC = os.path.expanduser(os.getenv("RAPID_TASK_SRC", ""))
APP_PYTHON = os.getenv("APP_PYTHON", sys.executable)  # interpreter that has the app's deps
SECRET_KEY = os.getenv("SECRET_KEY", "autotest-secret-key-not-for-production")
SERVER_START_TIMEOUT = int(os.getenv("SERVER_START_TIMEOUT", "60"))

# --- browser -----------------------------------------------------------------------
HEADLESS = os.getenv("HEADED", "0") != "1"
SLOW_MO = int(os.getenv("SLOW_MO", "0"))
UI_TIMEOUT_MS = int(os.getenv("UI_TIMEOUT_MS", "10000"))

# --- reporting ---------------------------------------------------------------------
REPORT_DIR = Path(os.getenv("REPORT_DIR", str(ROOT / "reports")))
VENDOR_DIR = ROOT / "vendor"

# --- test data ---------------------------------------------------------------------
PASSWORD = "Passw0rd!Autotest"
EMAIL_PREFIX = "qa_autotest_"
EMAIL_DOMAIN = "example.com"

# Mirrors of app limits (TEST_PLAN section 11: asserted against current implementation)
MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
DEFAULT_COLUMNS = ["Open", "ToDo", "In Progress", "Ready For Testing", "Testing",
                   "Ready for Deploy", "Deployed", "Done"]
