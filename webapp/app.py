"""ResidentChatBot web dashboard and admin interface.

The web layer is intentionally lightweight and uses only the Python standard
library so it can be deployed alongside the existing bot without adding a
framework dependency.
"""

from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from html import escape
import os
import subprocess
from typing import Iterable
from urllib.parse import parse_qs, urlparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import (
    DB_FILE,
    WEB_ADMIN_PASSWORD,
    WEB_ADMIN_USER,
    WEB_BASE_PATH,
    WEB_BIND_HOST,
    WEB_BIND_PORT,
    WEB_SERVICE_NAME,
)
from repositories.db import (
    get_dashboard_totals,
    get_pending_application_rows,
    get_recent_admin_actions,
    get_recent_application_rows,
    initialize_schema,
)


@dataclass(frozen=True)
class WebConfig:
    base_path: str = WEB_BASE_PATH
    bind_host: str = WEB_BIND_HOST
    bind_port: int = WEB_BIND_PORT
    admin_user: str = WEB_ADMIN_USER
    admin_password: str = WEB_ADMIN_PASSWORD
    service_name: str = WEB_SERVICE_NAME


CONFIG = WebConfig()


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        return f"/{path}"
    return path.rstrip("/") or "/"


def service_status(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        status = (result.stdout or result.stderr or "").strip()
        return status or "unknown"
    except Exception:
        return "unknown"


def format_value(value, default="—"):
    if value in (None, ""):
        return default
    return escape(str(value))


def fmt_ts(value):
    return format_value(value)


def app_status_label(status):
    labels = {
        "pending_review": "Ожидает проверки",
        "photo_requested_again": "Запрошено новое фото",
        "approved": "Одобрена",
        "denied": "Отклонена",
    }
    return labels.get(status, status or "неизвестно")


def build_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --panel-soft: #1f2937;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --ok: #10b981;
      --warn: #f59e0b;
      --bad: #ef4444;
      --line: rgba(148,163,184,.18);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0, var(--bg) 58%);
      color: var(--text);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{
      padding: 24px 0 8px;
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: end;
      flex-wrap: wrap;
    }}
    .hero h1 {{ margin: 0; font-size: 34px; }}
    .hero p {{ margin: 8px 0 0; color: var(--muted); max-width: 760px; }}
    .badge {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 999px;
      background: rgba(56,189,248,.12); color: var(--accent);
      border: 1px solid rgba(56,189,248,.24); font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin: 24px 0;
    }}
    .card, .panel {{
      background: rgba(17,24,39,.84);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 20px 45px rgba(2,6,23,.32);
    }}
    .card {{ padding: 18px; }}
    .card .k {{ color: var(--muted); font-size: 13px; }}
    .card .v {{ font-size: 30px; font-weight: 700; margin-top: 10px; }}
    .panels {{ display: grid; gap: 16px; grid-template-columns: 1.5fr 1fr; }}
    .panel {{ padding: 18px; }}
    .panel h2 {{ margin: 0 0 14px; font-size: 20px; }}
    .list {{ display: grid; gap: 10px; }}
    .row {{
      padding: 14px 16px;
      background: rgba(15,23,42,.56);
      border: 1px solid var(--line);
      border-radius: 14px;
    }}
    .row-head {{ display:flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    .muted {{ color: var(--muted); }}
    .pill {{
      display: inline-flex;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(56,189,248,.12);
      color: var(--accent);
      border: 1px solid rgba(56,189,248,.2);
      font-size: 12px;
      white-space: nowrap;
    }}
    .pill.ok {{ color: var(--ok); background: rgba(16,185,129,.12); border-color: rgba(16,185,129,.22); }}
    .pill.warn {{ color: var(--warn); background: rgba(245,158,11,.12); border-color: rgba(245,158,11,.22); }}
    .pill.bad {{ color: var(--bad); background: rgba(239,68,68,.12); border-color: rgba(239,68,68,.22); }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 13px; }}
    .footer-note {{ margin-top: 18px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 960px) {{
      .grid, .panels {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>"""


def render_dashboard(db_file: str = DB_FILE, service_name: str = CONFIG.service_name) -> str:
    stats = get_dashboard_totals(db_file)
    applications = get_recent_application_rows(db_file, limit=8)
    actions = get_recent_admin_actions(db_file, limit=6)
    status = service_status(service_name)
    body = [f"""
      <div class="hero">
        <div>
          <div class="badge">ResidentChatBot dashboard</div>
          <h1>Дашборд бота</h1>
          <p>Сводка по дому, пользователям и очереди заявок. Веб-часть использует ту же SQLite-базу, что и Telegram-бот.</p>
        </div>
        <div class="badge">service: {escape(service_name)} · {escape(status)}</div>
      </div>
      <div class="grid">
        <div class="card"><div class="k">Домов</div><div class="v">{stats["houses_total"]}</div></div>
        <div class="card"><div class="k">Активных жильцов</div><div class="v">{stats["active_users"]}</div></div>
        <div class="card"><div class="k">Pending заявок</div><div class="v">{stats["pending_applications"]}</div></div>
        <div class="card"><div class="k">Одобренных / отклонённых</div><div class="v">{stats["approved_applications"]} / {stats["denied_applications"]}</div></div>
      </div>
      <div class="panels">
        <section class="panel">
          <h2>Последние заявки</h2>
          <div class="list">
    """]
    if applications:
        for row in applications:
            app_id, tg_id, name, surname, apartment, phone, photo_file_id, app_status, reason, decision_note, created_at, updated_at, decided_at, decided_by, source_chat_id, house_chat_id, house_name = row
            body.append(
                f"""
                <div class="row">
                  <div class="row-head">
                    <strong>#{app_id} · {escape(app_status_label(app_status))}</strong>
                    <span class="pill">{escape(str(house_chat_id or source_chat_id or '—'))}</span>
                  </div>
                  <div class="muted">{escape(name or 'Без имени')} {escape(surname or '')} · кв. {escape(apartment or '—')} · tg_id={tg_id}</div>
                  <div class="muted">Телефон: {escape(phone or '—')}</div>
                  <div class="muted">Фото: {escape(photo_file_id or '—')}</div>
                  <div class="muted">Создана: {fmt_ts(created_at)} · Обновлена: {fmt_ts(updated_at)}</div>
                </div>
                """
            )
    else:
        body.append('<div class="row muted">Заявок пока нет.</div>')
    body.append("""
          </div>
        </section>
        <section class="panel">
          <h2>Последние действия</h2>
          <div class="list">
    """)
    if actions:
        for action_id, application_id, tg_id, action, note, created_at in actions:
            body.append(
                f"""
                <div class="row">
                  <div class="row-head">
                    <strong>{escape(action)}</strong>
                    <span class="pill">{escape(created_at or '—')}</span>
                  </div>
                  <div class="muted">application #{application_id} · tg_id={tg_id}</div>
                  <div class="muted">{escape(note or '—')}</div>
                </div>
                """
            )
    else:
        body.append('<div class="row muted">Действий пока нет.</div>')
    body.append("""
          </div>
        </section>
      </div>
      <div class="footer-note">
        Целевая веб-админка: <a href="adm">/adm</a>. Здесь только сводка и последние записи.
      </div>
    """)
    return build_layout("ResidentChatBot dashboard", "".join(body))


def render_admin(db_file: str = DB_FILE, service_name: str = CONFIG.service_name) -> str:
    pending = get_pending_application_rows(db_file, limit=30)
    recent_actions = get_recent_admin_actions(db_file, limit=12)
    status = service_status(service_name)
    body = [f"""
      <div class="hero">
        <div>
          <div class="badge">ResidentChatBot admin</div>
          <h1>Веб-админка</h1>
          <p>Наблюдение за очередью заявок и историей действий. На первом этапе интерфейс только читает данные из SQLite.</p>
        </div>
        <div class="badge">service: {escape(service_name)} · {escape(status)}</div>
      </div>
      <div class="panels">
        <section class="panel">
          <h2>Pending заявки</h2>
          <div class="list">
    """]
    if pending:
        for row in pending:
            app_id, tg_id, name, surname, apartment, phone, photo_file_id, app_status, reason, decision_note, created_at, updated_at, decided_at, decided_by, source_chat_id, house_chat_id, house_name = row
            body.append(
                f"""
                <div class="row">
                  <div class="row-head">
                    <strong>#{app_id} · {escape(app_status_label(app_status))}</strong>
                    <span class="pill warn">tg_id={tg_id}</span>
                  </div>
                  <div>{escape(name or 'Без имени')} {escape(surname or '')}</div>
                  <div class="muted">Дом: {escape(str(house_chat_id or source_chat_id or '—'))} · Квартира: {escape(apartment or '—')}</div>
                  <div class="muted">Телефон: {escape(phone or '—')}</div>
                  <div class="muted">Причина: {escape(reason or '—')}</div>
                  <div class="muted">Фото file_id: {escape(photo_file_id or '—')}</div>
                  <div class="muted">Создана: {fmt_ts(created_at)} · Обновлена: {fmt_ts(updated_at)}</div>
                </div>
                """
            )
    else:
        body.append('<div class="row muted">Pending заявок нет.</div>')
    body.append("""
          </div>
        </section>
        <section class="panel">
          <h2>История действий</h2>
          <div class="list">
    """)
    if recent_actions:
        for action_id, application_id, tg_id, action, note, created_at in recent_actions:
            body.append(
                f"""
                <div class="row">
                  <div class="row-head">
                    <strong>{escape(action)}</strong>
                    <span class="pill">{escape(created_at or '—')}</span>
                  </div>
                  <div class="muted">application #{application_id} · tg_id={tg_id}</div>
                  <div class="muted">{escape(note or '—')}</div>
                </div>
                """
            )
    else:
        body.append('<div class="row muted">История действий пуста.</div>')
    body.append("""
          </div>
        </section>
      </div>
      <div class="footer-note">
        Этот экран пока read-only. На следующем этапе здесь будут действия approve / deny / request photo.
      </div>
    """)
    return build_layout("ResidentChatBot admin", "".join(body))


def render_message_page(title: str, message: str, status: str = "ok") -> str:
    pill_class = "ok" if status == "ok" else "warn" if status == "warn" else "bad"
    body = f"""
      <div class="hero">
        <div>
          <div class="badge">ResidentChatBot</div>
          <h1>{escape(title)}</h1>
          <p>{escape(message)}</p>
        </div>
      </div>
      <div class="card">
        <span class="pill {pill_class}">{escape(status)}</span>
      </div>
    """
    return build_layout(title, body)


def parse_basic_auth(header_value: str | None) -> tuple[str, str] | None:
    if not header_value or not header_value.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
        if ":" not in decoded:
            return None
        return tuple(decoded.split(":", 1))
    except Exception:
        return None


def is_admin_authenticated(headers) -> bool:
    if not CONFIG.admin_password:
        return False
    credentials = parse_basic_auth(headers.get("Authorization"))
    if not credentials:
        return False
    username, password = credentials
    user_ok = hmac.compare_digest(username.encode("utf-8"), CONFIG.admin_user.encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), CONFIG.admin_password.encode("utf-8"))
    return user_ok and password_ok


class ResidentChatBotWebHandler(BaseHTTPRequestHandler):
    server_version = "ResidentChatBotWeb/0.1"

    def _send_html(self, html_text: str, status_code: int = HTTPStatus.OK, headers: Iterable[tuple[str, str]] = ()):
        encoded = html_text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, text: str, status_code: int = HTTPStatus.OK):
        encoded = text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _require_admin(self) -> bool:
        if is_admin_authenticated(self.headers):
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="ResidentChatBot admin"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        body = render_message_page("Доступ запрещён", "Нужна админская авторизация.", "warn").encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self):  # noqa: N802
        path = normalize_path(urlparse(self.path).path)
        base = normalize_path(CONFIG.base_path)
        if path == "/" or path == f"{base}/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", base)
            self.end_headers()
            return
        if path == base:
            if not self._require_admin():
                return
            self._send_html(render_dashboard())
            return
        if path == f"{base}/adm":
            if not self._require_admin():
                return
            self._send_html(render_admin())
            return
        if path == f"{base}/health":
            self._send_text("ok")
            return
        self._send_html(render_message_page("Не найдено", "Запрошенный маршрут не существует.", "bad"), HTTPStatus.NOT_FOUND)

    def log_message(self, format, *args):  # noqa: A003
        return


def create_server() -> ThreadingHTTPServer:
    initialize_schema(DB_FILE)
    return ThreadingHTTPServer((CONFIG.bind_host, CONFIG.bind_port), ResidentChatBotWebHandler)


def run_server():
    server = create_server()
    print(f"ResidentChatBot web listening on {CONFIG.bind_host}:{CONFIG.bind_port} with base {CONFIG.base_path}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
