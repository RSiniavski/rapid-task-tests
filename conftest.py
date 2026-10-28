"""Root fixtures: isolated application server, API clients, shared role users, per-test worlds."""
import pytest

from framework import config
from framework.client import Client
from framework.factory import Roles, build_world, register_user
from framework.server import AppServer

pytest_plugins = ["framework.report", "framework.ui_fixtures"]


# ---------------------------------------------------------------- server / clients
@pytest.fixture(scope="session")
def server():
    srv = AppServer.from_env().start()
    yield srv
    if srv.is_local:
        srv.stop()


@pytest.fixture(scope="session")
def base_url(server):
    return server.base_url


@pytest.fixture(scope="session")
def anon(base_url) -> Client:
    return Client(base_url)


@pytest.fixture
def db(server):
    """Direct SQL access to the isolated test database (local server only)."""
    if not server.is_local:
        pytest.skip("needs a locally spawned server (BASE_URL mode has no DB access)")
    return server.sql


@pytest.fixture
def uploads_dir(server):
    if not server.is_local:
        pytest.skip("needs a locally spawned server (BASE_URL mode has no filesystem access)")
    return server.uploads_dir


@pytest.fixture
def local_server(server):
    if not server.is_local:
        pytest.skip("needs a locally spawned server")
    return server


@pytest.fixture(scope="session")
def secret_key(server):
    if not server.is_local:
        pytest.skip("forging tokens needs the SECRET_KEY of a locally spawned server")
    return config.SECRET_KEY


# ---------------------------------------------------------------- users and projects
@pytest.fixture(scope="session")
def roles(base_url, server):
    """Long-lived users shared by read-mostly tests. Tests that deactivate/delete users create
    their own throw-away users via `make_user`."""
    r = Roles(
        admin=register_user(base_url, "QA Admin", tag="adm_"),
        editor=register_user(base_url, "QA Editor", tag="edt_"),
        contributor=register_user(base_url, "QA Contributor", tag="ctr_"),
        reporter=register_user(base_url, "QA Reporter", tag="rep_"),
        outsider=register_user(base_url, "QA Outsider", tag="out_"),
    )
    yield r
    if not server.is_local:  # external instance: remove everything the suite created
        _cleanup_external(base_url, r.admin)


def _cleanup_external(base_url: str, any_user) -> None:
    c = any_user.client
    users = c.get("/api/users").json()
    for u in users:
        if u["email"].startswith(config.EMAIL_PREFIX) and u["id"] != any_user.id:
            c.delete(f"/api/users/{u['id']}", params={"hard_delete": "true"})
    c.delete(f"/api/users/{any_user.id}", params={"hard_delete": "true"})


@pytest.fixture
def world(roles):
    """Project A (all four roles are members) and project B (separate, owned by the outsider)."""
    return build_world(roles)


@pytest.fixture
def on_board(world):
    """Tickets of project A get an open milestone, so the board shows them (board rule)."""
    return world.a.use_default_milestone()


@pytest.fixture
def make_user(base_url):
    """Factory for throw-away users: make_user(tag='x', full_name=None)."""
    def _make(**kw):
        return register_user(base_url, **kw)
    return _make
