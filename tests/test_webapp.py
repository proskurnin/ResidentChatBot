import base64
import importlib
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from repositories.db import ensure_house_exists, initialize_schema, insert_application


@pytest.fixture
def webapp_module(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_ID", "42")
    monkeypatch.setenv("WEB_ADMIN_USER", "admin")
    monkeypatch.setenv("WEB_ADMIN_PASSWORD", "secret")
    monkeypatch.delenv("WEB_BIND_HOST", raising=False)
    for name in ("config", "webapp.app"):
        sys.modules.pop(name, None)
    module = importlib.import_module("webapp.app")
    monkeypatch.setattr(module, "service_status", lambda service_name: "active")
    return module


@pytest.fixture
def web_server(webapp_module, monkeypatch):
    monkeypatch.setattr(webapp_module, "render_dashboard", lambda: "dashboard-page")
    monkeypatch.setattr(webapp_module, "render_admin", lambda: "admin-page")
    server = ThreadingHTTPServer(("127.0.0.1", 0), webapp_module.ResidentChatBotWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}{webapp_module.CONFIG.base_path}"
    server.shutdown()
    server.server_close()


def fetch(url, credentials=None):
    request = urllib.request.Request(url)
    if credentials:
        token = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def test_bind_host_defaults_to_localhost(webapp_module):
    assert webapp_module.CONFIG.bind_host == "127.0.0.1"


@pytest.mark.parametrize("path", ["", "/adm"])
def test_pages_with_resident_data_require_auth(web_server, path):
    assert fetch(web_server + path)[0] == 401
    assert fetch(web_server + path, "admin:wrong")[0] == 401
    assert fetch(web_server + path, "other:secret")[0] == 401
    status, body = fetch(web_server + path, "admin:secret")
    assert status == 200
    assert body == ("admin-page" if path else "dashboard-page")


def test_health_is_public(web_server):
    assert fetch(web_server + "/health") == (200, "ok")


def test_empty_password_denies_everyone(webapp_module, monkeypatch):
    monkeypatch.setattr(webapp_module, "CONFIG", webapp_module.WebConfig(admin_user="admin", admin_password=""))
    token = base64.b64encode(b"admin:").decode("ascii")
    assert webapp_module.is_admin_authenticated({"Authorization": f"Basic {token}"}) is False


def test_dashboard_escapes_resident_data(webapp_module, tmp_path):
    db_file = tmp_path / "test.db"
    initialize_schema(db_file)
    house_id = ensure_house_exists(db_file, 10001, "2026-05-22T10:00:00")
    insert_application(
        db_file, 555, None, house_id, 10001, "<script>alert(1)</script>", "Petrov", "12",
        "+79990000000", "photo-1", "pending_review", "2026-05-22T10:00:00", "2026-05-22T10:00:00",
    )

    for html_text in (webapp_module.render_dashboard(db_file), webapp_module.render_admin(db_file)):
        assert "<script>alert(1)</script>" not in html_text
        assert "&lt;script&gt;" in html_text
