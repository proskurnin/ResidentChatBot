import importlib
import sys
import types
from pathlib import Path

import pytest


class DummyBot:
    def __init__(self, *args, **kwargs):
        self.sent_messages = []
        self.sent_photos = []
        self.answers = []
        self.restrict_calls = []
        self.kick_calls = []
        self.unban_calls = []
        self.delete_calls = []
        self.edit_calls = []
        self.next_step_calls = []
        self.callback_handlers = []
        self.message_handlers = []
        self.me = types.SimpleNamespace(id=999, username="ResidentChatBot")

    def message_handler(self, *args, **kwargs):
        def decorator(func):
            self.message_handlers.append((func, kwargs))
            return func

        return decorator

    def callback_query_handler(self, *args, **kwargs):
        def decorator(func):
            self.callback_handlers.append((func, kwargs))
            return func

        return decorator

    def register_callback_query_handler(self, handler, *args, **kwargs):
        self.callback_handlers.append((handler, kwargs))
        return handler

    def register_next_step_handler_by_chat_id(self, chat_id, func):
        self.next_step_calls.append((chat_id, func))

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append((chat_id, text, reply_markup))
        return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), text=text)

    def send_photo(self, chat_id, photo, reply_markup=None):
        self.sent_photos.append((chat_id, photo, reply_markup))

    def answer_callback_query(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    def restrict_chat_member(self, chat_id, user_id, **kwargs):
        self.restrict_calls.append((chat_id, user_id, kwargs))

    def kick_chat_member(self, chat_id, user_id):
        self.kick_calls.append((chat_id, user_id))

    def unban_chat_member(self, chat_id, user_id):
        self.unban_calls.append((chat_id, user_id))

    def delete_message(self, chat_id, message_id):
        self.delete_calls.append((chat_id, message_id))

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.edit_calls.append((chat_id, message_id, reply_markup))

    def get_me(self):
        return self.me

    def get_chat(self, chat_id):
        return types.SimpleNamespace(title=f"Chat {chat_id}", username=f"chat{chat_id}")

    def get_chat_member(self, chat_id, user_id):
        return types.SimpleNamespace(
            status="member",
            user=types.SimpleNamespace(first_name="Ivan", username="ivan"),
        )

    def polling(self):
        raise AssertionError("polling should not be called in unit tests")


def make_message(chat_id, user_id, text=None, chat_type="private", first_name="Ivan", username="ivan",
                 photo_id="photo-1", new_chat_members=None, left_chat_member=None):
    message = types.SimpleNamespace(
        chat=types.SimpleNamespace(id=chat_id, type=chat_type),
        from_user=types.SimpleNamespace(id=user_id, first_name=first_name, username=username),
        text=text,
        new_chat_members=new_chat_members or [],
        left_chat_member=left_chat_member,
    )
    if photo_id is not None:
        message.photo = [types.SimpleNamespace(file_id=photo_id)]
    return message


def make_call(data, user_id, chat_id=10, chat_type="private", first_name="Ivan", username="ivan"):
    return types.SimpleNamespace(
        data=data,
        id=f"cb-{data}",
        message=types.SimpleNamespace(
            chat=types.SimpleNamespace(id=chat_id, type=chat_type),
            message_id=1,
        ),
        from_user=types.SimpleNamespace(id=user_id, first_name=first_name, username=username),
    )


def load_main_module(monkeypatch, proxy_url=None):
    monkeypatch.setenv("API_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_ID", "42")
    monkeypatch.setenv("BOT_NAME", "ResidentChatBot")
    if proxy_url is None:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        monkeypatch.delenv("https_proxy", raising=False)
    else:
        monkeypatch.setenv("HTTP_PROXY", proxy_url)
        monkeypatch.setenv("HTTPS_PROXY", proxy_url)

    import telebot

    monkeypatch.setattr(telebot, "TeleBot", DummyBot)
    sys.modules.pop("main", None)
    sys.modules.pop("config", None)
    sys.modules.pop("registration", None)

    source = Path("main.py").read_text(encoding="utf-8")
    cutoff = source.index("\n# ====================================================================\n# Запуск бота\n# ====================================================================\n")
    module = types.ModuleType("main")
    module.__file__ = str(Path("main.py").resolve())
    sys.modules["main"] = module
    exec(compile(source[:cutoff], module.__file__, "exec"), module.__dict__)
    return module


def load_registration_module(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_ID", "42")
    monkeypatch.setenv("BOT_NAME", "ResidentChatBot")
    sys.modules.pop("config", None)
    sys.modules.pop("registration", None)
    return importlib.import_module("registration")


@pytest.fixture
def temp_db(tmp_path):
    return tmp_path / "test.db"
