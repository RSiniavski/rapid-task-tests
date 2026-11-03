"""Fixtures for the platform (admin tool) tests. Loaded as a pytest plugin from conftest.py."""
import pytest

from framework import config
from framework.platform_api import P, create_admin, login_client
from framework.server import AppServer


@pytest.fixture(scope="session")
def proot(server, base_url):
    """A client logged in as the root admin of the isolated test server (its credentials are known)."""
    if not server.is_local:
        pytest.skip("platform tests need a locally spawned server (they know its root credentials)")
    return login_client(base_url, config.PLATFORM_ROOT_USERNAME, config.PLATFORM_ROOT_PASSWORD)


@pytest.fixture
def padmin(proot, base_url):
    """Factory: padmin(tag, **fields) creates a platform admin (permissions off by default) and logs it in.
    The admins are deleted after the test."""
    made = []

    def make(tag: str = "adm", **fields):
        admin = create_admin(proot, base_url, tag, **fields)
        made.append(admin)
        return admin

    yield make
    for admin in made:
        try:
            proot.delete(f"{P}/admins/{admin.id}")
        except Exception:                      # the test may have deleted it already
            pass


@pytest.fixture
def plt_server():
    """Factory: plt_server(env) starts an extra isolated application with its own databases.
    env = extra environment, a value of None removes the variable (e.g. the root account)."""
    if config.BASE_URL:
        pytest.skip("needs a locally spawned server")
    made = []

    def make(env=None, label="plt"):
        srv = AppServer.from_env(label=label, env_overrides=env or {}).start()
        made.append(srv)
        return srv

    yield make
    for srv in made:
        srv.stop()


@pytest.fixture
def plogin_ui(context):
    """plogin_ui(admin_or_client, **local) -> the browser opens platform.html already signed in.
    Accepts a PAdmin (from padmin) or a Client (proot). Extra keyword arguments are more localStorage items."""
    from framework.ui_fixtures import seed_session

    def _login(who, **local):
        token = getattr(who, "token", None) or who.client.token
        seed_session(context, None, "en", extra_local={"rt_platform_token": token, **local})
    return _login
