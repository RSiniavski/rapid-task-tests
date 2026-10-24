"""Starts an isolated copy of the application (own SQLite DB + uploads dir) or wraps BASE_URL.

The application resolves its DB (`./rapid_task.db`), `static/` and `uploads/` relative to the
working directory / package location, so we copy the source tree into a fresh temp directory
and run uvicorn there. The developer's database and uploads are never touched.
"""
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests

from framework import config

_IGNORE = shutil.ignore_patterns("*.db", "*.db-journal", "uploads", "__pycache__", "*.pyc", ".git",
                                 ".venv", "venv", ".env", "tests", "node_modules", ".pytest_cache")


def _find_src() -> Path:
    candidates = []
    if config.APP_SRC:
        candidates.append(Path(config.APP_SRC))
    here = config.ROOT
    candidates += [here.parent / "rapid task", here.parent / "rapid_task", here.parent / "rapid-task",
                   here / "rapid task", here / "app_under_test"]
    for c in candidates:
        if (c / "app" / "main.py").is_file() and (c / "static").is_dir():
            return c.resolve()
    raise RuntimeError(
        f"Looked in: {[str(c) for c in candidates]}\n"
        "Cannot locate the application under test. Set RAPID_TASK_SRC=/path/to/project "
        "(folder containing app/ and static/) or BASE_URL=http://host:port.")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppServer:
    """Either a locally spawned isolated instance or an external one (BASE_URL)."""

    def __init__(self, external_url: str = "", src: Optional[Path] = None, legacy_db: Optional[Path] = None,
                 label: str = "main"):
        self.external = bool(external_url)
        self._url = external_url
        self.src = src
        self.legacy_db = legacy_db
        self.label = label
        self.workdir: Optional[Path] = None
        self.proc: Optional[subprocess.Popen] = None
        self.log_path: Optional[Path] = None
        self.port = 0

    # ---- properties
    @property
    def base_url(self) -> str:
        return self._url

    @property
    def is_local(self) -> bool:
        return not self.external

    @property
    def db_path(self) -> Optional[Path]:
        return self.workdir / "rapid_task.db" if self.workdir else None

    @property
    def uploads_dir(self) -> Optional[Path]:
        return self.workdir / "uploads" if self.workdir else None

    # ---- lifecycle
    @classmethod
    def from_env(cls, **kw) -> "AppServer":
        if config.BASE_URL:
            return cls(external_url=config.BASE_URL, **kw)
        return cls(src=_find_src(), **kw)

    def start(self) -> "AppServer":
        if self.external:
            self._wait_ready()
            return self
        self.workdir = Path(tempfile.mkdtemp(prefix=f"rt_autotest_{self.label}_"))
        shutil.copytree(self.src, self.workdir, ignore=_IGNORE, dirs_exist_ok=True)
        (self.workdir / "uploads").mkdir(exist_ok=True)
        if self.legacy_db:
            shutil.copy(self.legacy_db, self.workdir / "rapid_task.db")
        self._spawn()
        return self

    def _spawn(self) -> None:
        self.port = _free_port()
        self._url = f"http://127.0.0.1:{self.port}"
        self.log_path = self.workdir / f"server_{self.port}.log"
        env = dict(os.environ, SECRET_KEY=config.SECRET_KEY, PYTHONDONTWRITEBYTECODE="1",
                   NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [config.APP_PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=str(self.workdir), env=env, stdout=log, stderr=subprocess.STDOUT)
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.time() + config.SERVER_START_TIMEOUT
        last = ""
        s = requests.Session()
        s.trust_env = False
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"Application exited during start-up:\n{self.log_text()}")
            try:
                if s.get(self._url + "/openapi.json", timeout=2).status_code == 200:
                    return
            except requests.RequestException as exc:
                last = str(exc)
            time.sleep(0.3)
        raise RuntimeError(f"Application did not become ready at {self._url}: {last}\n{self.log_text()}")

    def log_text(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")[-4000:] if self.log_path else ""
        except OSError:
            return ""

    def stop(self, cleanup: bool = True) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
        if cleanup and self.workdir and self.workdir.exists():
            shutil.rmtree(self.workdir, ignore_errors=True)

    def restart(self) -> None:
        """Stop and start the process again on the SAME database (idempotent start-up checks)."""
        assert self.is_local
        self.stop(cleanup=False)
        self._spawn()

    # ---- direct DB access (local only)
    def sql(self, query: str, params: tuple = ()) -> list:
        assert self.db_path, "direct DB access requires a locally spawned server"
        con = sqlite3.connect(str(self.db_path), timeout=15)
        try:
            cur = con.execute(query, params)
            rows = cur.fetchall()
            con.commit()
            return rows
        finally:
            con.close()
