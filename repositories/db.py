"""SQLite helpers for ResidentChatBot."""

from contextlib import contextmanager
import sqlite3


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS houses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        house_name TEXT,
        chat_id INTEGER UNIQUE,
        house_city TEXT,
        house_address TEXT,
        date_add TEXT,
        date_del TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        name TEXT,
        surname TEXT,
        house INTEGER,
        apartment TEXT,
        phone TEXT,
        date_add TEXT,
        date_del TEXT,
        FOREIGN KEY(house) REFERENCES houses(id),
        UNIQUE(tg_id, house)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user INTEGER,
        autonum TEXT,
        date_add TEXT,
        date_del TEXT,
        FOREIGN KEY(user) REFERENCES users(id)
    )
    """,
)


@contextmanager
def connect(db_file):
    conn = sqlite3.connect(db_file)
    try:
        yield conn
    finally:
        conn.close()


def initialize_schema(db_file):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        conn.commit()


def get_house_id_by_chat_id(db_file, chat_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_house_chat_rows_by_user_tg(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT h.chat_id, h.house_name
            FROM houses h
            JOIN users u ON u.house = h.id
            WHERE u.tg_id = ?
            """,
            (tg_id,),
        )
        return cursor.fetchall()


def ensure_house_exists(db_file, chat_id, date_add):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor.execute("INSERT INTO houses (chat_id, date_add) VALUES (?, ?)", (chat_id, date_add))
        conn.commit()
        return cursor.lastrowid


def insert_user(db_file, tg_id, name, house_id=None):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        if house_id is None:
            cursor.execute("INSERT INTO users (tg_id, name) VALUES (?, ?)", (tg_id, name))
        else:
            cursor.execute("INSERT INTO users (tg_id, house, name) VALUES (?, ?, ?)", (tg_id, house_id, name))
        conn.commit()
        return cursor.lastrowid


def update_user_name_by_id(db_file, user_id, name, date_add=None):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        if date_add is None:
            cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
        else:
            cursor.execute("UPDATE users SET name = ?, date_add = ? WHERE id = ?", (name, date_add, user_id))
        conn.commit()


def update_user_surname_by_id(db_file, user_id, surname):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET surname = ? WHERE id = ?", (surname, user_id))
        conn.commit()


def update_user_apartment_by_id(db_file, user_id, apartment, house_id=None):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        if house_id is None:
            cursor.execute("UPDATE users SET apartment = ? WHERE id = ?", (apartment, user_id))
        else:
            cursor.execute("UPDATE users SET apartment = ?, house = ? WHERE id = ?", (apartment, house_id, user_id))
        conn.commit()


def update_user_phone_by_id(db_file, user_id, phone):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
        conn.commit()


def update_user_date_add_date_del_by_tg_and_house(db_file, tg_id, house_id, date_add):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET date_add = ?, date_del = NULL WHERE tg_id = ? AND house = ?",
            (date_add, tg_id, house_id),
        )
        conn.commit()


def update_user_house_date_add_date_del_by_tg_null_house(db_file, tg_id, house_id, date_add):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET house = ?, date_add = ?, date_del = NULL WHERE tg_id = ? AND house IS NULL",
            (house_id, date_add, tg_id),
        )
        conn.commit()


def mark_user_date_del_by_tg_and_house(db_file, tg_id, house_id, date_del):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        if house_id is None:
            cursor.execute("UPDATE users SET date_del = ? WHERE tg_id = ? AND house IS NULL", (date_del, tg_id))
        else:
            cursor.execute("UPDATE users SET date_del = ? WHERE tg_id = ? AND house = ?", (date_del, tg_id, house_id))
        conn.commit()


def activate_cars_by_tg(db_file, tg_id, date_add):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET date_del = NULL, date_add = ? WHERE user IN (SELECT id FROM users WHERE tg_id = ?)",
            (date_add, tg_id),
        )
        conn.commit()


def mark_cars_date_del_by_tg(db_file, tg_id, date_del):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET date_del = ? WHERE user IN (SELECT id FROM users WHERE tg_id = ?)",
            (date_del, tg_id),
        )
        conn.commit()


def mark_cars_date_del_by_user_id(db_file, user_id, date_del):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cars SET date_del = ? WHERE user = ? AND (date_del IS NULL OR date_del = '')",
            (date_del, user_id),
        )
        conn.commit()


def insert_car_for_user(db_file, user_id, autonum):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cars (user, autonum) VALUES (?, ?)", (user_id, autonum))
        conn.commit()


def get_user_record_by_tg_and_house(db_file, tg_id, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, date_del FROM users WHERE tg_id = ? AND house = ?",
            (tg_id, house_id),
        )
        return cursor.fetchone()


def get_user_record_by_tg_and_null_house(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, date_del FROM users WHERE tg_id = ? AND house IS NULL",
            (tg_id,),
        )
        return cursor.fetchone()


def get_user_basic_profile_by_tg(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, surname, apartment, phone FROM users WHERE tg_id = ?",
            (tg_id,),
        )
        return cursor.fetchone()


def get_user_registration_profile_by_tg(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, surname, phone FROM users WHERE tg_id = ? LIMIT 1",
            (tg_id,),
        )
        return cursor.fetchone()


def get_any_user_id_by_tg(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE tg_id = ? LIMIT 1", (tg_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_user_full_record_by_tg_and_house(db_file, tg_id, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, date_del FROM users WHERE tg_id = ? AND house = ?",
            (tg_id, house_id),
        )
        return cursor.fetchone()


def get_user_id_by_tg_and_house(db_file, tg_id, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE tg_id = ? AND house = ?", (tg_id, house_id))
        row = cursor.fetchone()
        return row[0] if row else None


def get_user_id_by_tg_and_null_house(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE tg_id = ? AND house IS NULL", (tg_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_last_user_id_by_tg_and_house(db_file, tg_id, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        if house_id is None:
            cursor.execute("SELECT MAX(id) FROM users WHERE tg_id = ? AND house IS NULL", (tg_id,))
        else:
            cursor.execute("SELECT MAX(id) FROM users WHERE tg_id = ? AND house = ?", (tg_id, house_id))
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None


def count_active_users_by_house(db_file, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE house = ? AND (date_del IS NULL OR date_del = '')",
            (house_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def get_active_user_tg_ids_by_house(db_file, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tg_id FROM users WHERE house = ? AND (date_del IS NULL OR date_del = '')",
            (house_id,),
        )
        return cursor.fetchall()


def get_active_user_rows_by_house(db_file, house_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tg_id, name, surname, apartment, phone, date_add
            FROM users
            WHERE house = ? AND (date_del IS NULL OR date_del = '')
            ORDER BY apartment, name, tg_id
            """,
            (house_id,),
        )
        return cursor.fetchall()


def search_active_user_rows_by_apartment(db_file, house_id, apartment):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT tg_id, name, surname, apartment, phone, date_add
            FROM users
            WHERE house = ? AND apartment = ? AND (date_del IS NULL OR date_del = '')
            ORDER BY name, tg_id
            """,
            (house_id, apartment),
        )
        return cursor.fetchall()


def get_active_house_rows(db_file):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, id FROM houses")
        return cursor.fetchall()


def get_active_user_count_by_tg(db_file, tg_id):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE tg_id = ? AND (date_del IS NULL OR date_del = '')",
            (tg_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0


def dump_tables_text(db_file):
    with connect(db_file) as conn:
        cursor = conn.cursor()
        output = "Таблица houses\n id | house_name | chat_id | house_city | house_address | date_add | date_del \n"
        cursor.execute("SELECT * FROM houses")
        for row in cursor.fetchall():
            output += " | ".join(map(str, row)) + "\n"
        output += "\nТаблица users\n id | tg_id | name | surname | house | apartment | phone | date_add | date_del \n"
        cursor.execute("SELECT * FROM users")
        for row in cursor.fetchall():
            output += " | ".join(map(str, row)) + "\n"
        output += "\nТаблица cars\n id | user | autonum | date_add | date_del \n"
        cursor.execute("SELECT * FROM cars")
        for row in cursor.fetchall():
            output += " | ".join(map(str, row)) + "\n"
        return output
