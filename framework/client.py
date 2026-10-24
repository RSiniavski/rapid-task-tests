"""Thin HTTP client used by every API/E2E test."""
from typing import Optional
from urllib.parse import urlparse

import requests


class Client:
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        host = urlparse(self.base_url).hostname or ""
        if host in ("127.0.0.1", "localhost", "::1"):
            self.session.trust_env = False  # never route local traffic through a proxy

    def with_token(self, token: Optional[str]) -> "Client":
        return Client(self.base_url, token)

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def request(self, method: str, path: str, *, auth: bool = True, headers: Optional[dict] = None,
                timeout: int = 60, **kw) -> requests.Response:
        h = dict(self.headers) if auth else {}
        h.update(headers or {})
        return self.session.request(method, self.base_url + path, headers=h, timeout=timeout, **kw)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def upload(self, path: str, filename: str, content: bytes, content_type: str,
               params: Optional[dict] = None, field: str = "file", **kw) -> requests.Response:
        return self.post(path, params=params, files={field: (filename, content, content_type)}, **kw)

    def login_form(self, username: str, password: str) -> requests.Response:
        return self.post("/api/auth/login", auth=False, data={"username": username, "password": password})
