"""MIG-01 / MIG-02: start-up on a fresh DB is repeatable; a legacy DB is upgraded without data loss."""
import sqlite3

import pytest

from framework.client import Client
from framework.factory import ok, register_user
from framework.server import AppServer

pytestmark = [pytest.mark.api, pytest.mark.needs_local_server]


@pytest.fixture
def own_server(server):
    if not server.is_local:
        pytest.skip("needs a locally spawned server")
    return server


@pytest.mark.plan("MIG-01")
def test_fresh_database_has_all_tables_and_current_columns():
    srv = AppServer.from_env(label="fresh").start()
    try:
        tables = {r[0] for r in srv.sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "projects", "project_members", "board_columns", "tickets", "ticket_history",
                "ticket_attachments", "milestones", "roadmap_dependencies"} <= tables
        cols = lambda t: {r[1] for r in srv.sql(f"PRAGMA table_info({t})")}  # noqa: E731
        assert {"position", "avatar_path"} <= cols("users")
        assert "milestone_id" in cols("tickets")
        assert {"progress", "pos_x", "pos_y"} <= cols("milestones")
        assert srv.uploads_dir.is_dir()
    finally:
        srv.stop()


@pytest.mark.plan("MIG-01")
def test_restart_is_idempotent_and_keeps_data():
    srv = AppServer.from_env(label="restart").start()
    try:
        u = register_user(srv.base_url)
        proj = ok(u.client.post("/api/projects", json={"name": "Persist", "key": "PRS"}), 201).json()
        before = srv.sql("SELECT sql FROM sqlite_master ORDER BY name")
        for _ in range(2):
            srv.restart()
        assert srv.sql("SELECT sql FROM sqlite_master ORDER BY name") == before
        u2 = Client(srv.base_url)
        login = ok(u2.login_form(u.email, u.password)).json()
        assert login["access_token"]
        got = ok(u2.with_token(login["access_token"]).get(f"/api/projects/{proj['id']}")).json()
        assert got["name"] == "Persist"
        assert len(srv.sql("SELECT id FROM board_columns WHERE project_id=?", (proj["id"],))) == 8
        assert Client(srv.base_url).get("/openapi.json").status_code == 200
    finally:
        srv.stop()


LEGACY_SQL = """
CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR NOT NULL UNIQUE, hashed_password VARCHAR NOT NULL,
  full_name VARCHAR NOT NULL, is_active BOOLEAN NOT NULL DEFAULT 1, created_at DATETIME);
CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, key VARCHAR NOT NULL UNIQUE,
  project_type VARCHAR NOT NULL DEFAULT 'SOFTWARE_DEV', language VARCHAR NOT NULL DEFAULT 'uk',
  ticket_seq INTEGER NOT NULL DEFAULT 0, owner_id INTEGER NOT NULL, created_at DATETIME);
CREATE TABLE project_members (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  role VARCHAR NOT NULL, created_at DATETIME);
CREATE TABLE board_columns (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, name VARCHAR NOT NULL,
  position INTEGER NOT NULL, is_done BOOLEAN NOT NULL DEFAULT 0);
CREATE TABLE tickets (id INTEGER PRIMARY KEY, key VARCHAR NOT NULL UNIQUE, title VARCHAR NOT NULL, description TEXT,
  type VARCHAR NOT NULL DEFAULT 'TASK', project_id INTEGER NOT NULL, column_id INTEGER NOT NULL, parent_id INTEGER,
  assignee_id INTEGER, tester_id INTEGER, reporter_id INTEGER NOT NULL, created_at DATETIME, closed_at DATETIME);
CREATE TABLE milestones (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, title VARCHAR NOT NULL,
  description TEXT, start_date DATETIME, due_date DATETIME, status VARCHAR, color VARCHAR NOT NULL DEFAULT '#fff',
  position_x FLOAT NOT NULL DEFAULT 0, position_y FLOAT NOT NULL DEFAULT 0, created_at DATETIME);
CREATE INDEX ix_milestones_project_id ON milestones (project_id);
"""


def _legacy_db(path):
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SQL)
    # bcrypt hash is irrelevant: legacy users never log in here
    con.execute("INSERT INTO users (id,email,hashed_password,full_name) VALUES (1,'old@example.com','x','Old User')")
    con.execute("INSERT INTO projects (id,name,key,owner_id,ticket_seq) VALUES (1,'Legacy','LEG',1,1)")
    con.execute("INSERT INTO project_members (project_id,user_id,role) VALUES (1,1,'ADMIN')")
    con.execute("INSERT INTO board_columns (id,project_id,name,position,is_done) VALUES (1,1,'Open',0,0),(2,1,'Done',1,1)")
    con.execute("INSERT INTO tickets (id,key,title,project_id,column_id,reporter_id) VALUES (1,'LEG-1','Old ticket',1,1,1)")
    con.execute("INSERT INTO milestones (id,project_id,title,start_date,due_date,status,position_x,position_y) VALUES "
                "(1,1,'Old A','2030-01-01 00:00:00','2030-02-01 00:00:00','active',11.5,22.5),"
                "(2,1,'Old B',NULL,NULL,'completed',3,4),"
                "(3,1,'Old C',NULL,NULL,'weird',0,0)")
    con.commit()
    con.close()


@pytest.mark.plan("MIG-02")
def test_legacy_database_is_migrated_with_data_preserved(tmp_path):
    legacy = tmp_path / "legacy.db"
    _legacy_db(legacy)
    srv = AppServer.from_env(label="legacy", legacy_db=legacy).start()
    try:
        cols = lambda t: {r[1] for r in srv.sql(f"PRAGMA table_info({t})")}  # noqa: E731
        assert {"position", "avatar_path"} <= cols("users")
        assert "milestone_id" in cols("tickets")
        assert {"progress", "pos_x", "pos_y"} <= cols("milestones")
        assert not ({"color", "position_x", "position_y"} & cols("milestones"))
        rows = {r[0]: r for r in srv.sql("SELECT id,title,start_date,due_date,status,progress,pos_x,pos_y FROM milestones")}
        assert rows[1][2:] == ("2030-01-01", "2030-02-01", "in_progress", 0, 11.5, 22.5)
        assert rows[2][4:6] == ("done", 100) and rows[3][4] == "planned"
        assert srv.sql("SELECT title FROM tickets WHERE key='LEG-1'") == [("Old ticket",)]
        assert not [r for r in srv.sql("SELECT name FROM sqlite_master WHERE name LIKE 'milestones_legacy%'")]

        # the migrated database is fully usable through the API
        u = register_user(srv.base_url)
        proj = ok(u.client.post("/api/projects", json={"name": "New", "key": "NEW"}), 201).json()
        m = ok(u.client.post(f"/api/roadmap/project/{proj['id']}/milestones", json={"title": "Fresh"}), 201).json()
        assert m["status"] == "planned"
        assert ok(u.client.get(f"/api/roadmap/project/{proj['id']}")).status_code == 200

        # second start-up must not change anything (idempotent)
        snapshot = srv.sql("SELECT id,title,status,progress,pos_x,pos_y FROM milestones ORDER BY id")
        srv.restart()
        assert srv.sql("SELECT id,title,status,progress,pos_x,pos_y FROM milestones ORDER BY id") == snapshot
    finally:
        srv.stop()
