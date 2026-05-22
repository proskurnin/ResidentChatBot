import types
from datetime import datetime

from repositories.db import (
    count_active_users_by_house,
    ensure_house_exists,
    get_active_user_count_by_tg,
    get_house_id_by_chat_id,
    get_user_basic_profile_by_tg,
    get_user_record_by_tg_and_house,
    initialize_schema,
    insert_car_for_user,
    insert_user,
    mark_cars_date_del_by_tg,
    mark_user_date_del_by_tg_and_house,
    update_user_apartment_by_id,
)

from tests.conftest import DummyBot, load_main_module, load_registration_module, make_call, make_message


def configure_modules(main_module, temp_db):
    registration = main_module.registration
    bot = main_module.bot
    main_module.DB_FILE = temp_db
    main_module.pending_users = {}
    main_module.user_state = {}
    main_module.admin_state = {}
    main_module.ADMIN_ID = 42
    main_module.BOT_NAME = "ResidentChatBot"
    registration.DB_FILE = temp_db
    registration.pending_users = main_module.pending_users
    registration.user_state = main_module.user_state
    registration.bot = bot
    return registration, bot


def find_message_handler(bot, *, commands=None, content_types=None, name=None):
    for handler, kwargs in bot.message_handlers:
        if name is not None and handler.__name__ != name:
            continue
        if commands is not None and kwargs.get("commands") != commands:
            continue
        if content_types is not None and kwargs.get("content_types") != content_types:
            continue
        return handler
    raise AssertionError(f"Handler not found: name={name}, commands={commands}, content_types={content_types}")


def test_registration_flow_and_confirmation(monkeypatch, temp_db):
    registration = load_registration_module(monkeypatch)
    bot = DummyBot()
    registration.bot = bot
    registration.DB_FILE = temp_db
    registration.pending_users = {1: {"source_chat_id": 1111}}
    registration.user_state = {}

    registration.ask_registration_confirmation(10, 1)
    assert bot.sent_messages[-1][0] == 10
    assert "Вы регистрируетесь" in bot.sent_messages[-1][1]

    captured = []
    monkeypatch.setattr(registration, "ask_name", lambda chat_id, user_id: captured.append((chat_id, user_id)))
    registration.handle_registration_confirmation(make_call("confirm_1", 1))
    assert captured == [(10, 1)]

    bot.sent_messages.clear()
    bot.kick_calls.clear()
    registration.handle_registration_confirmation(make_call("decline_1", 1))
    assert bot.kick_calls[-1] == (1111, 1)
    assert any("удалить" in text for _, text, _ in bot.sent_messages)


def test_registration_data_flow(monkeypatch, temp_db):
    registration = load_registration_module(monkeypatch)
    bot = DummyBot()
    registration.bot = bot
    registration.DB_FILE = temp_db
    registration.pending_users = {1: {"source_chat_id": 1001}}
    registration.user_state = {}
    initialize_schema(temp_db)

    registration.process_name(make_message(10, 1, text="Ivan"), 1)
    assert get_user_basic_profile_by_tg(temp_db, 1)[0] == "Ivan"
    assert bot.next_step_calls[-1][0] == 10
    assert bot.sent_messages[-1][1] == "Фамилия:"

    registration.process_surname(make_message(10, 1, text="Petrov"), 1)
    assert get_user_basic_profile_by_tg(temp_db, 1)[1] == "Petrov"
    assert bot.sent_messages[-1][1] == "№ квартиры:"

    registration.user_state[1] = "awaiting_apartment_new_house"
    house_id = get_house_id_by_chat_id(temp_db, 1001)
    registration.process_apartment(make_message(10, 1, text="12"), 1)
    assert get_user_record_by_tg_and_house(temp_db, 1, house_id)[0] is not None
    assert bot.sent_messages[-1][1].startswith("Отлично!")

    registration.user_state[1] = {}
    registration.process_phone(make_message(10, 1, text="+79990000000"), 1)
    assert get_user_basic_profile_by_tg(temp_db, 1)[3] == "+79990000000"
    assert bot.sent_messages[-1][1] == "Укажите, сколько у вас автомобилей (0 если нет):"

    registration.process_car_count(make_message(10, 1, text="0"), 1)
    assert registration.user_state[1] == "awaiting_photo"
    assert "Анкета заполнена" in bot.sent_messages[-1][1]

    registration.user_state[1] = {}
    registration.process_car_count(make_message(10, 1, text="1"), 1)
    assert registration.user_state[1]["current_car"] == 1
    registration.process_car_number(make_message(10, 1, text="A123BC777"), 1)
    assert registration.user_state[1] == "awaiting_photo"


def test_registration_negative_paths(monkeypatch, temp_db):
    registration = load_registration_module(monkeypatch)
    bot = DummyBot()
    registration.bot = bot
    registration.DB_FILE = temp_db
    registration.pending_users = {}
    registration.user_state = {}
    initialize_schema(temp_db)
    ensure_house_exists(temp_db, 1111, "2026-05-22T10:00:00")

    assert registration.get_current_house_id(1) is None

    registration.ask_registration_confirmation(10, 1)
    assert "Вы готовы" in bot.sent_messages[-1][1]

    registration.pending_users = {1: {"source_chat_id": 1111}}
    registration.handle_registration_confirmation(make_call("decline_1", 1))
    assert bot.kick_calls[-1] == (1111, 1)

    bot.sent_messages.clear()
    registration.process_name(make_message(10, 1, text="A" * 51), 1)
    assert "Имя не должно превышать" in bot.sent_messages[-1][1]
    registration.process_name(make_message(10, 1, text="сука"), 1)
    assert "недопустимые слова" in bot.sent_messages[-1][1]

    user_id = insert_user(temp_db, 1, "Ivan", 1)
    registration.pending_users = {1: {"source_chat_id": 1111}}
    registration.process_name(make_message(10, 1, text="Petr"), 1)
    assert get_user_basic_profile_by_tg(temp_db, 1)[0] == "Petr"

    bot.sent_messages.clear()
    registration.process_surname(make_message(10, 1, text="A" * 51), 1)
    assert "Фамилия не должна превышать" in bot.sent_messages[-1][1]
    registration.process_surname(make_message(10, 1, text="сука"), 1)
    assert "недопустимые слова" in bot.sent_messages[-1][1]

    bot.sent_messages.clear()
    registration.process_apartment(make_message(10, 1, text="abc"), 1)
    assert "Ошибка:" in bot.sent_messages[-1][1]
    registration.process_apartment(make_message(10, 1, text="10001"), 1)
    assert "Ошибка:" in bot.sent_messages[-1][1]

    bot.sent_messages.clear()
    registration.process_phone(make_message(10, 1, text="123"), 1)
    assert "Неверный формат телефона" in bot.sent_messages[-1][1]

    bot.sent_messages.clear()
    registration.process_car_count(make_message(10, 1, text="11"), 1)
    assert "Количество авто должно быть" in bot.sent_messages[-1][1]
    registration.process_car_number(make_message(10, 1, text="ab"), 1)
    assert "Номер авто должен содержать" in bot.sent_messages[-1][1]


def test_main_registration_and_admin_handlers(monkeypatch, temp_db):
    main_module = load_main_module(monkeypatch)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    house_id = ensure_house_exists(temp_db, 1001, "2026-05-22T10:00:00")
    other_house_id = ensure_house_exists(temp_db, 2002, "2026-05-22T10:00:00")
    user_7_id = insert_user(temp_db, 7, "Ivan", house_id)
    update_user_apartment_by_id(temp_db, user_7_id, "12")

    assert main_module.get_source_chat_id(7) == 1001
    bot.sent_messages.clear()
    main_module.pending_users.pop(7, None)
    insert_user(temp_db, 7, "Ivan", other_house_id)
    assert main_module.get_source_chat_id(7) is None
    assert any("Выберите чат пользователя" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    bot.answers.clear()
    main_module.choose_source_handler(make_call("choose_source:7:3003", 42, chat_id=42))
    assert main_module.pending_users[7]["source_chat_id"] == "3003"
    assert bot.sent_messages[-1][0] == 42

    # Existing user with no date_del.
    main_module.pending_users[7] = {"source_chat_id": 1001}
    bot.sent_messages.clear()
    main_module.start_introduction_handler(make_call("start_introduction", 7, chat_id=1001))
    assert "мы тебя узнали" in bot.sent_messages[-1][1]

    # Existing confirmed user.
    mark_user_date_del_by_tg_and_house(temp_db, 7, house_id, "2026-05-22T11:00:00")
    bot.sent_messages.clear()
    main_module.start_introduction_handler(make_call("start_introduction", 7, chat_id=1001))
    assert "Хотите вернуться в группу" in bot.sent_messages[-1][1]

    # New user path.
    bot.sent_messages.clear()
    main_module.start_introduction_handler(make_call("start_introduction", 99, chat_id=4004))
    assert "Вы готовы приступить к регистрации" in bot.sent_messages[-1][1]

    # New member.
    bot.sent_messages.clear()
    new_member = types.SimpleNamespace(id=50, first_name="Petr")
    main_module.new_member_handler(make_message(5005, 60, chat_type="group", new_chat_members=[new_member]))
    assert main_module.pending_users[50]["source_chat_id"] == 5005
    assert bot.restrict_calls[-1][:2] == (5005, 50)

    # Photo flow.
    main_module.user_state[50] = "awaiting_photo"
    main_module.pending_users[50] = {"source_chat_id": 5005}
    user_50_id = insert_user(temp_db, 50, "Petr", None)
    update_user_apartment_by_id(temp_db, user_50_id, "18")
    bot.sent_messages.clear()
    main_module.photo_handler(make_message(10, 50, chat_type="private", photo_id="file-1"))
    assert main_module.user_state[50] == "photo_sent"
    assert any(msg[0] == 42 for msg in bot.sent_messages)

    # Allow / deny / request photo / save reason.
    main_module.pending_users[50] = {"source_chat_id": 5005}
    bot.sent_messages.clear()
    main_module.allow_access(make_call("allow:50", 42, chat_id=42))
    house_for_5005 = get_house_id_by_chat_id(temp_db, 5005)
    assert get_user_record_by_tg_and_house(temp_db, 50, house_for_5005) is not None

    main_module.pending_users[51] = {"source_chat_id": 5005}
    insert_user(temp_db, 51, "Sergey", house_for_5005)
    bot.sent_messages.clear()
    main_module.deny_access(make_call("deny:51", 42, chat_id=42))
    assert bot.kick_calls[-1] == (5005, 51)

    main_module.pending_users[52] = {"source_chat_id": 5005}
    insert_user(temp_db, 52, "Alex", house_for_5005)
    main_module.request_photo(make_call("request_photo:52", 42, chat_id=42))
    assert main_module.admin_state[42]["awaiting_reason"] is True
    main_module.save_reason(make_message(42, 42, text="blurry photo", chat_type="private"))
    assert main_module.user_state[52] == "awaiting_new_photo"
    assert main_module.admin_state == {}

    # Left chat member and not residing.
    main_module.pending_users[53] = {"source_chat_id": 5005}
    user_53_id = insert_user(temp_db, 53, "Nina", house_for_5005)
    insert_car_for_user(temp_db, user_53_id, "A111AA77")
    main_module.left_member_handler(make_message(5005, 60, chat_type="group", left_chat_member=types.SimpleNamespace(id=53)))
    assert get_active_user_count_by_tg(temp_db, 53) == 0

    main_module.pending_users[54] = {"source_chat_id": 5005}
    insert_user(temp_db, 54, "Dmitry", house_for_5005)
    main_module.not_residing_handler(make_call("not_residing", 54, chat_id=5005, chat_type="group"))
    assert bot.kick_calls[-1] == (5005, 54)

    main_module.return_yes_handler(make_call("return_yes", 54, chat_id=5005, chat_type="group"))
    assert main_module.user_state[54] == "awaiting_photo"
    main_module.return_no_handler(make_call("return_no", 54, chat_id=5005, chat_type="group"))
    main_module.identification_handler(make_call("identification", 54, chat_id=5005, chat_type="group"))

    # Confirm residence + registration callbacks.
    main_module.pending_users[55] = {"source_chat_id": 5005}
    main_module.confirm_residence_handler(make_call("confirm_residence", 55, chat_id=5005))
    assert any("Ответьте на несколько вопросов" in msg[1] for msg in bot.sent_messages)
    main_module.confirm_registration_yes_handler(make_call("confirm_registration_yes", 55, chat_id=5005))
    assert bot.sent_messages[-1][1] == "Ваше имя:"
    main_module.confirm_registration_no_handler(make_call("confirm_registration_no", 55, chat_id=5005))
    assert bot.kick_calls[-1] == (5005, 55)

    # Commands.
    admin_message = make_message(42, 42, text="/db", chat_type="private")
    main_module.db_handler(admin_message)
    assert any("Таблица houses" in msg[1] for msg in bot.sent_messages)
    main_module.check_handler(make_message(42, 42, text="/check 5005", chat_type="private"))
    main_module.checkall_handler(make_message(42, 42, text="/checkall", chat_type="private"))


def test_main_negative_paths_and_new_house_registration(monkeypatch, temp_db):
    main_module = load_main_module(monkeypatch)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    house_id = ensure_house_exists(temp_db, 1111, "2026-05-22T10:00:00")
    user_id = insert_user(temp_db, 8, "Olga", house_id)
    update_user_apartment_by_id(temp_db, user_id, "7")

    start_handler = find_message_handler(bot, commands=["start"])
    newuser_handler = find_message_handler(bot, commands=["newuser"])

    bot.sent_messages.clear()
    start_handler(make_message(1111, 8, chat_type="group"))
    assert bot.sent_messages == []

    start_handler(make_message(8, 8, chat_type="private"))
    assert any("Выбирай задачу" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    newuser_handler(make_message(8, 8, chat_type="private"))
    assert any("нужно познакомиться" in msg[1] for msg in bot.sent_messages)
    assert bot.sent_messages[-1][2] is not None

    # New house registration for an already known user.
    bot.sent_messages.clear()
    new_house_chat = 2222
    ensure_house_exists(temp_db, new_house_chat, "2026-05-22T10:00:00")
    main_module.pending_users[8] = {"source_chat_id": new_house_chat}
    result = main_module.start_introduction_handler(make_call("start_introduction", 8, chat_id=new_house_chat))
    assert result is None
    assert main_module.user_state[8] == "awaiting_apartment_new_house"
    assert any("нового дома" in msg[1] for msg in bot.sent_messages)

    # Error / empty branches.
    bot.sent_messages.clear()
    main_module.user_state.pop(8, None)
    main_module.photo_handler(make_message(8, 8, chat_type="private", photo_id="file-x"))
    assert bot.sent_messages == []

    main_module.user_state[8] = "awaiting_photo"
    main_module.pending_users.pop(8, None)
    main_module.photo_handler(make_message(8, 8, chat_type="private", photo_id="file-x"))
    assert any("уточнение чата" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    main_module.pending_users[8] = {"source_chat_id": house_id}
    main_module.request_photo(make_call("request_photo:8", 42, chat_id=42))
    assert main_module.admin_state[42]["awaiting_reason"] is True
    bot.sent_messages.clear()
    main_module.admin_state.clear()
    main_module.save_reason(make_message(42, 42, text="ignored", chat_type="private"))
    assert bot.sent_messages == []

    bot.sent_messages.clear()
    main_module.identification_handler(types.SimpleNamespace(message=types.SimpleNamespace(chat=None), from_user=types.SimpleNamespace(id=8)))
    assert bot.sent_messages == []
    main_module.not_residing_handler(make_call("not_residing", 8, chat_id=8, chat_type="group"))
    assert any("Чат предназначен только для жильцов" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    main_module.db_handler(make_message(9, 9, text="/db", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Нет доступа"

    bot.sent_messages.clear()
    main_module.check_handler(make_message(42, 42, text="/check", chat_type="private"))
    assert "Укажите ID группы" in bot.sent_messages[-1][1]

    bot.sent_messages.clear()
    main_module.check_handler(make_message(42, 42, text="/check -999", chat_type="private"))
    assert any("не найден дом" in msg[1] or "нет зарегистрированных" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    main_module.check_handler(make_message(9, 9, text="/check -999", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Нет доступа."

    bot.sent_messages.clear()
    main_module.checkall_handler(make_message(42, 42, text="/checkall", chat_type="private"))
    assert any("Группа" in msg[1] or "Нет данных" in msg[1] for msg in bot.sent_messages)

    bot.sent_messages.clear()
    main_module.checkall_handler(make_message(9, 9, text="/checkall", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Нет доступа."


def test_main_callbacks_and_proxy(monkeypatch, temp_db):
    proxy_url = "http://proxy.local:8080"
    main_module = load_main_module(monkeypatch, proxy_url=proxy_url)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    import telebot

    assert telebot.apihelper.proxy == {"http": proxy_url, "https": proxy_url}

    # Placeholder callbacks.
    main_module.info_placeholder_handler(make_call("info_placeholder", 8, chat_id=8))
    main_module.admin_placeholder_handler(make_call("admin_placeholder", 8, chat_id=8))
    assert bot.sent_messages[-1][1] == "Функция пока не реализована"

    # Return-to-group callbacks.
    bot.sent_messages.clear()
    main_module.return_yes_handler(make_call("return_yes", 8, chat_id=8))
    assert main_module.user_state[8] == "awaiting_photo"
    main_module.return_no_handler(make_call("return_no", 8, chat_id=8))
    assert bot.sent_messages[-1][1] == "Ну, заходи если чё..."

    # call.message.chat is None branch.
    main_module.identification_handler(types.SimpleNamespace(message=types.SimpleNamespace(chat=None), from_user=types.SimpleNamespace(id=8)))

    # No source_chat branches.
    bot.sent_messages.clear()
    main_module.pending_users.clear()
    main_module.allow_access(make_call("allow:8", 42, chat_id=42))
    assert bot.sent_messages[-1][1] == "Ожидайте, идет уточнение чата администраторами."

    bot.sent_messages.clear()
    main_module.deny_access(make_call("deny:8", 42, chat_id=42))
    assert bot.sent_messages[-1][1] == "Ожидайте, идет уточнение чата администраторами."

    bot.sent_messages.clear()
    main_module.request_photo(make_call("request_photo:8", 42, chat_id=42))
    assert bot.sent_messages[-1][1] == "Ожидайте, идет уточнение чата администраторами."

    # confirm_registration callbacks.
    called = []
    monkeypatch.setattr(registration, "ask_name", lambda chat_id, user_id: called.append((chat_id, user_id)))
    main_module.pending_users[8] = {"source_chat_id": 5555}
    ensure_house_exists(temp_db, 5555, "2026-05-22T10:00:00")
    main_module.confirm_registration_yes_handler(make_call("confirm_registration_yes", 8, chat_id=8))
    assert called == [(8, 8)]
    main_module.confirm_registration_no_handler(make_call("confirm_registration_no", 8, chat_id=8))
    assert bot.kick_calls[-1] == (5555, 8)

    # Empty and not-found checks.
    bot.sent_messages.clear()
    empty_db = temp_db.parent / "empty.db"
    initialize_schema(empty_db)
    main_module.DB_FILE = empty_db
    main_module.checkall_handler(make_message(42, 42, text="/checkall", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Нет данных по группам."

    main_module.DB_FILE = temp_db
    house_id = ensure_house_exists(temp_db, 5555, "2026-05-22T10:00:00")
    bot.sent_messages.clear()
    main_module.check_handler(make_message(42, 42, text="/check 5555", chat_type="private"))
    assert "нет зарегистрированных пользователей" in bot.sent_messages[-1][1]


def test_main_status_transitions_and_fallbacks(monkeypatch, temp_db):
    main_module = load_main_module(monkeypatch)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    source_chat_id = 5005
    house_id = ensure_house_exists(temp_db, source_chat_id, "2026-05-22T10:00:00")
    other_house_id = ensure_house_exists(temp_db, 6006, "2026-05-22T10:00:00")

    # start_introduction: existing user moves to a new house, but registration profile is missing.
    insert_user(temp_db, 14, "Olga", other_house_id)
    main_module.pending_users[14] = {"source_chat_id": source_chat_id}
    monkeypatch.setattr(main_module, "get_user_registration_profile_by_tg", lambda *args, **kwargs: None)
    bot.sent_messages.clear()
    main_module.start_introduction_handler(make_call("start_introduction", 14, chat_id=source_chat_id))
    assert main_module.user_state[14] == "awaiting_apartment_new_house"
    assert any("нового дома" in msg[1] for msg in bot.sent_messages)

    # allow_access: create pending_users entry and move it to approved.
    insert_user(temp_db, 15, "Sergey", None)
    original_get_source_chat_id = main_module.get_source_chat_id
    monkeypatch.setattr(main_module, "get_source_chat_id", lambda user_id: source_chat_id if user_id == 15 else original_get_source_chat_id(user_id))
    bot.sent_messages.clear()
    main_module.pending_users.pop(15, None)
    main_module.allow_access(make_call("allow:15", 42, chat_id=42))
    assert main_module.pending_users[15]["status"] == "approved"
    assert get_user_record_by_tg_and_house(temp_db, 15, house_id) is not None

    # photo_handler: fallback profile path and photo_sent transition.
    main_module.user_state[16] = "awaiting_photo"
    main_module.pending_users[16] = {"source_chat_id": source_chat_id}
    bot.sent_messages.clear()
    bot.sent_photos.clear()
    main_module.photo_handler(make_message(16, 16, text=None, chat_type="private", first_name="Petr", photo_id="file-16"))
    assert main_module.user_state[16] == "photo_sent"
    assert bot.sent_photos[-1][0] == 42
    assert any("Имя: Petr" in msg[1] for msg in bot.sent_messages)

    # request_photo + save_reason: admin state -> awaiting_reason -> awaiting_new_photo.
    main_module.pending_users[17] = {"source_chat_id": source_chat_id}
    main_module.request_photo(make_call("request_photo:17", 42, chat_id=42))
    assert main_module.admin_state[42]["awaiting_reason"] is True
    bot.sent_messages.clear()
    main_module.save_reason(make_message(42, 42, text="blurred image", chat_type="private"))
    assert main_module.user_state[17] == "awaiting_new_photo"
    assert 42 not in main_module.admin_state

    # save_reason: src_chat missing branch stays defensive.
    main_module.pending_users[21] = {}
    main_module.admin_state[42] = {"user_id": 21, "awaiting_reason": True}
    bot.sent_messages.clear()
    main_module.save_reason(make_message(42, 42, text="ignored", chat_type="private"))
    assert main_module.user_state[21] == "awaiting_new_photo"
    assert 42 not in main_module.admin_state

    # save_reason: missing user_id branch stays defensive.
    main_module.admin_state[42] = {"awaiting_reason": True}
    bot.sent_messages.clear()
    main_module.save_reason(make_message(42, 42, text="ignored", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Не найден user_id для ADMIN_ID."

    # left_member_handler: clears pending_users after a leave event.
    user_18_id = insert_user(temp_db, 18, "Nina", house_id)
    insert_car_for_user(temp_db, user_18_id, "A111AA77")
    main_module.pending_users[18] = {"source_chat_id": source_chat_id}
    main_module.left_member_handler(
        make_message(source_chat_id, 99, chat_type="group", left_chat_member=types.SimpleNamespace(id=18))
    )
    assert 18 not in main_module.pending_users
    assert get_active_user_count_by_tg(temp_db, 18) == 0

    # return_yes: user moves back to awaiting_photo.
    main_module.user_state[19] = "awaiting_new_photo"
    main_module.return_yes_handler(make_call("return_yes", 19, chat_id=source_chat_id, chat_type="group"))
    assert main_module.user_state[19] == "awaiting_photo"

    # confirm_residence: no record -> start registration flow.
    called = []
    monkeypatch.setattr(registration, "ask_name", lambda chat_id, user_id: called.append((chat_id, user_id)))
    main_module.pending_users[20] = {"source_chat_id": source_chat_id}
    main_module.confirm_residence_handler(make_call("confirm_residence", 20, chat_id=source_chat_id))
    assert called == [(source_chat_id, 20)]


def test_repeat_callbacks_and_exception_branches(monkeypatch, temp_db):
    main_module = load_main_module(monkeypatch)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    source_chat_id = 7007
    house_id = ensure_house_exists(temp_db, source_chat_id, "2026-05-22T10:00:00")

    # Repeat callback: the same confirmation callback can be triggered more than once.
    ask_name_calls = []
    monkeypatch.setattr(registration, "ask_name", lambda chat_id, user_id: ask_name_calls.append((chat_id, user_id)))
    main_module.confirm_registration_yes_handler(make_call("confirm_registration_yes", 30, chat_id=source_chat_id))
    main_module.confirm_registration_yes_handler(make_call("confirm_registration_yes", 30, chat_id=source_chat_id))
    assert ask_name_calls == [(source_chat_id, 30), (source_chat_id, 30)]

    # confirm_residence existing-user branch with return flow keyboard.
    insert_user(temp_db, 31, "Ivan", house_id)
    update_user_apartment_by_id(temp_db, get_user_record_by_tg_and_house(temp_db, 31, house_id)[0], "12")
    mark_user_date_del_by_tg_and_house(temp_db, 31, house_id, "2026-05-22T12:00:00")
    bot.sent_messages.clear()
    main_module.pending_users[31] = {"source_chat_id": source_chat_id}
    main_module.confirm_residence_handler(make_call("confirm_residence", 31, chat_id=source_chat_id))
    assert any("Хотите вернуться в группу" in msg[1] for msg in bot.sent_messages)

    # registration.handle_registration_confirmation decline exception branch.
    registration.pending_users = {32: {"source_chat_id": source_chat_id}}
    bot.kick_calls.clear()
    bot.sent_messages.clear()
    monkeypatch.setattr(bot, "kick_chat_member", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    registration.handle_registration_confirmation(make_call("decline_32", 32, chat_id=source_chat_id))
    assert any("удалить из чата" in msg[1] for msg in bot.sent_messages)

    # registration.process_name exception branch.
    bot.sent_messages.clear()
    monkeypatch.setattr(registration, "insert_user", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("name")))
    registration.pending_users = {33: {"source_chat_id": source_chat_id}}
    registration.user_state = {}
    registration.process_name(make_message(33, 33, text="Petr"), 33)
    assert bot.sent_messages[-1][1] == "Произошла ошибка при сохранении данных, попробуйте позже."

    # registration.process_surname exception branch.
    bot.sent_messages.clear()
    insert_user(temp_db, 33, "Petr", house_id)
    monkeypatch.setattr(registration, "update_user_surname_by_id", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("surname")))
    registration.process_surname(make_message(33, 33, text="Petrov"), 33)
    assert any("Произошла ошибка при сохранении данных, попробуйте позже." == msg[1] for msg in bot.sent_messages)

    # registration.process_apartment missing record branch.
    bot.sent_messages.clear()
    registration.user_state[34] = "awaiting_apartment_new_house"
    registration.pending_users[34] = {"source_chat_id": source_chat_id}
    monkeypatch.setattr(registration, "get_last_user_id_by_tg_and_house", lambda *args, **kwargs: None)
    registration.process_apartment(make_message(34, 34, text="12"), 34)
    assert bot.sent_messages[-1][1] == "Произошла ошибка при обновлении данных, попробуйте позже."

    # registration.process_phone exception branch.
    bot.sent_messages.clear()
    insert_user(temp_db, 35, "Ivan", house_id)
    monkeypatch.setattr(registration, "update_user_phone_by_id", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("phone")))
    registration.user_state[35] = {}
    registration.pending_users[35] = {"source_chat_id": source_chat_id}
    registration.process_phone(make_message(35, 35, text="+79990000000"), 35)
    assert any("Произошла ошибка при сохранении данных, попробуйте позже." == msg[1] for msg in bot.sent_messages)

    # registration.process_car_number exception branch and multi-car continuation.
    bot.sent_messages.clear()
    insert_user(temp_db, 36, "Nina", house_id)
    registration.user_state[36] = {"car_count": 2, "current_car": 1}
    registration.pending_users[36] = {"source_chat_id": source_chat_id}
    monkeypatch.setattr(registration, "insert_car_for_user", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("car")))
    registration.process_car_number(make_message(36, 36, text="A123BC77"), 36)
    assert any("Произошла ошибка при сохранении данных, попробуйте позже." == msg[1] for msg in bot.sent_messages)

    # Restore insert_car_for_user to verify the repeat-next-step path for multi-car flow.
    monkeypatch.setattr(registration, "insert_car_for_user", lambda *args, **kwargs: None)
    bot.sent_messages.clear()
    registration.process_car_number(make_message(36, 36, text="A123BC77"), 36)
    assert registration.user_state[36]["current_car"] == 2
    assert bot.next_step_calls[-1][0] == 36

    # main.confirm_registration_no_handler exception branch.
    bot.sent_messages.clear()
    monkeypatch.setattr(bot, "kick_chat_member", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("kick")))
    monkeypatch.setattr(bot, "unban_chat_member", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unban")))
    main_module.pending_users[37] = {"source_chat_id": source_chat_id}
    main_module.confirm_registration_no_handler(make_call("confirm_registration_no", 37, chat_id=source_chat_id))
    assert bot.sent_messages[-1][1] == "Чат предназначен только для жителей дома. Сейчас мы вас из него удалим."


def test_admin_reports_commands(monkeypatch, temp_db):
    main_module = load_main_module(monkeypatch)
    registration, bot = configure_modules(main_module, temp_db)
    initialize_schema(temp_db)

    house_id = ensure_house_exists(temp_db, 8080, "2026-05-22T10:00:00")
    user_1 = insert_user(temp_db, 101, "Ivan", house_id)
    update_user_apartment_by_id(temp_db, user_1, "12")
    user_2 = insert_user(temp_db, 102, "Petr", house_id)
    update_user_apartment_by_id(temp_db, user_2, "12")
    update_user_apartment_by_id(temp_db, user_2, "12")

    main_module.pending_users[201] = {
        "source_chat_id": 8080,
        "status": "awaiting_photo",
        "reason": "blurry",
        "join_time": datetime(2026, 5, 22, 12, 0, 0),
    }
    main_module.pending_users[202] = {
        "source_chat_id": 9090,
        "status": "awaiting_reason",
    }

    # /pending report
    bot.sent_messages.clear()
    main_module.pending_handler(make_message(42, 42, text="/pending", chat_type="private"))
    assert any("Pending-заявки:" in msg[1] for msg in bot.sent_messages)
    assert any("user 201" in msg[1] for msg in bot.sent_messages)

    # /users report
    bot.sent_messages.clear()
    main_module.users_handler(make_message(42, 42, text="/users 8080", chat_type="private"))
    assert any("Активные пользователи группы 8080" in msg[1] for msg in bot.sent_messages)
    assert any("кв. 12" in msg[1] for msg in bot.sent_messages)

    # /apartment report
    bot.sent_messages.clear()
    main_module.apartment_handler(make_message(42, 42, text="/apartment 8080 12", chat_type="private"))
    assert any("Квартира 12" in msg[1] for msg in bot.sent_messages)

    # access control and validation
    bot.sent_messages.clear()
    main_module.pending_handler(make_message(9, 9, text="/pending", chat_type="private"))
    assert bot.sent_messages[-1][1] == "Нет доступа."

    bot.sent_messages.clear()
    main_module.users_handler(make_message(42, 42, text="/users", chat_type="private"))
    assert "Укажите ID группы" in bot.sent_messages[-1][1]

    bot.sent_messages.clear()
    main_module.apartment_handler(make_message(42, 42, text="/apartment 8080", chat_type="private"))
    assert "Укажите ID группы и номер квартиры" in bot.sent_messages[-1][1]
