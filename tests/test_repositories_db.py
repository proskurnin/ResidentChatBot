import sqlite3

from repositories.db import (
    count_active_users_by_house,
    dump_tables_text,
    ensure_house_exists,
    get_active_user_count_by_tg,
    get_house_id_by_chat_id,
    get_user_basic_profile_by_tg,
    get_user_record_by_tg_and_house,
    initialize_schema,
    insert_car_for_user,
    insert_user,
    mark_cars_date_del_by_user_id,
    mark_user_date_del_by_tg_and_house,
    update_user_apartment_by_id,
    update_user_name_by_id,
    update_user_phone_by_id,
    update_user_surname_by_id,
)


def fetch_row(db_file, query, params=()):
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()


def test_repository_helpers_support_basic_user_flow(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_schema(db_file)

    house_id = ensure_house_exists(db_file, 10001, "2026-05-22T10:00:00")
    assert house_id == get_house_id_by_chat_id(db_file, 10001)
    assert ensure_house_exists(db_file, 10001, "2026-05-22T11:00:00") == house_id

    user_id = insert_user(db_file, 555, "Ivan", house_id)
    update_user_name_by_id(db_file, user_id, "Ivan", "2026-05-22T12:00:00")
    update_user_surname_by_id(db_file, user_id, "Petrov")
    update_user_apartment_by_id(db_file, user_id, "12")
    update_user_phone_by_id(db_file, user_id, "+79990000000")

    assert get_user_record_by_tg_and_house(db_file, 555, house_id) == (user_id, "Ivan", None)
    assert get_user_basic_profile_by_tg(db_file, 555) == ("Ivan", "Petrov", "12", "+79990000000")

    insert_car_for_user(db_file, user_id, "A123BC777")
    mark_cars_date_del_by_user_id(db_file, user_id, "2026-05-22T13:00:00")
    mark_user_date_del_by_tg_and_house(db_file, 555, house_id, "2026-05-22T13:30:00")

    assert count_active_users_by_house(db_file, house_id) == 0
    assert get_active_user_count_by_tg(db_file, 555) == 0

    user_row = fetch_row(
        db_file,
        "SELECT date_add, date_del FROM users WHERE id = ?",
        (user_id,),
    )
    assert user_row == ("2026-05-22T12:00:00", "2026-05-22T13:30:00")

    car_row = fetch_row(
        db_file,
        "SELECT autonum, date_del FROM cars WHERE user = ?",
        (user_id,),
    )
    assert car_row == ("A123BC777", "2026-05-22T13:00:00")

    dump_text = dump_tables_text(db_file)
    assert "Таблица houses" in dump_text
    assert "Таблица users" in dump_text
    assert "Таблица cars" in dump_text
