import importlib
import sys


def import_config_with_env(monkeypatch, **env):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_config_reads_expected_values(monkeypatch):
    config = import_config_with_env(
        monkeypatch,
        API_TOKEN="token-123",
        ADMIN_ID="42",
        BOT_NAME="ResidentChatBot",
        LOG_LEVEL="debug",
        HTTPS_PROXY="http://proxy.local:8080",
    )

    assert config.API_TOKEN == "token-123"
    assert config.ADMIN_ID == 42
    assert config.BOT_NAME == "ResidentChatBot"
    assert config.LOG_LEVEL_NAME == "DEBUG"
    assert config.TELEGRAM_PROXY == "http://proxy.local:8080"


def test_config_rejects_non_integer_admin_id(monkeypatch):
    sys.modules.pop("config", None)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("API_TOKEN", "token-123")
    monkeypatch.setenv("ADMIN_ID", "not-an-int")
    monkeypatch.setenv("BOT_NAME", "ResidentChatBot")

    try:
        importlib.import_module("config")
    except ValueError as exc:
        assert "ADMIN_ID должен быть целым числом" in str(exc)
    else:
        raise AssertionError("config should reject non-integer ADMIN_ID")
