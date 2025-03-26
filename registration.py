"""
Модуль регистрации нового пользователя и анкетирования.
Этот модуль отвечает за последовательное получение данных от пользователя через чат-бота,
включая имя, фамилию, номер квартиры, телефон, информацию об автомобилях и фото территории.
"""

# Импорт необходимых модулей:
from datetime import datetime  # Для получения текущей даты и времени
import sqlite3                # Для работы с базой данных SQLite
import logging                # Для ведения логов
import phonenumbers           # Для валидации и форматирования телефонных номеров
from phonenumbers import PhoneNumberFormat, format_number  # Константы и функции для форматирования номеров
from telebot import types

# Глобальные переменные, которые будут инициализированы из main.py
# bot - экземпляр чат-бота, DB_FILE - путь к файлу базы данных,
# pending_users - словарь с информацией о пользователях, находящихся в процессе регистрации,
# user_state - словарь для отслеживания текущего состояния регистрации каждого пользователя
bot = None
DB_FILE = None
pending_users = None
user_state = None

def ask_registration_confirmation(chat_id, user_id):
    """
    Отправляет сообщение с подтверждением регистрации и двумя кнопками:
      - "Да, и готов подтвердить"
      - "Нет, я не живу в этом доме"
    """
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id')
    markup = types.InlineKeyboardMarkup(row_width=1)
    yes_button = types.InlineKeyboardButton(text="Да, и готов подтвердить", callback_data=f"confirm_{user_id}")
    no_button = types.InlineKeyboardButton(text="Нет, я не живу в этом доме", callback_data=f"decline_{user_id}")
    markup.add(yes_button, no_button)
    message_text = (f"Вы регистрируетесь в чате ({source_chat_id}). Для того чтобы подтвердить ваше проживание дома, "
                    f"на последнем шаге регистрации вам потребуется прислать актуальное фото из окна вашей квартиры. "
                    f"Вы готовы приступить к регистрации?")
    bot.send_message(chat_id, message_text, reply_markup=markup)

def handle_registration_confirmation(call):
    """
    Обрабатывает ответ пользователя на запрос регистрации.
    Если выбран вариант подтверждения, запускается процесс регистрации (ask_name).
    Если выбран отказ, пользователю отправляется сообщение об удалении из чата, затем происходит удаление
    и в исходный чат отправляется уведомление.
    """
    data = call.data
    if data.startswith("confirm_"):
        user_id = int(data.split("_")[1])
        # Убираем клавиатуру после выбора
        # bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        # Запускаем процесс регистрации
        ask_name(call.message.chat.id, user_id)
    elif data.startswith("decline_"):
        user_id = int(data.split("_")[1])
        chat_id = call.message.chat.id
        bot.send_message(chat_id, "Чат предназначен только для жителей дома и мы вынуждены вас удалить из чата")
        source_chat_id = pending_users.get(user_id, {}).get('source_chat_id')
        if source_chat_id:
            try:
                bot.kick_chat_member(source_chat_id, user_id)
            except Exception as e:
                logging.error(f"Ошибка при удалении пользователя {user_id} из чата {source_chat_id}: {e}")
            user_first_name = call.from_user.first_name if call.from_user.first_name else "сосед"
            bot.send_message(source_chat_id, f"Пользователь @{user_first_name} удалён из чата, потому что отказался проходить регистрацию")

def register_confirmation_handler():
    """
    Регистрирует обработчик callback-запросов для подтверждения регистрации.
    """
    bot.register_callback_query_handler(handle_registration_confirmation, func=lambda call: call.data.startswith("confirm_") or call.data.startswith("decline_"))

def init_registration(b, db_file, p_users, u_state):
    """
    Инициализирует модуль регистрации глобальными переменными, полученными из main.py.
    """
    global bot, DB_FILE, pending_users, user_state
    bot = b
    DB_FILE = db_file
    pending_users = p_users
    user_state = u_state
    register_confirmation_handler()


def ask_name(chat_id, user_id):
    # Отправка сообщения с запросом имени пользователю
    bot.send_message(chat_id, "Ваше имя:")
    # Регистрация обработчика следующего шага, который вызовет функцию process_name
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_name(message, user_id))


def process_name(message, user_id):
    # Удаляем лишние пробелы из введённого имени
    name = message.text.strip()

    # Проверка длины имени: если имя длиннее 50 символов, отправляем сообщение об ошибке
    if len(name) > 50:
        bot.send_message(message.chat.id, "Имя не должно превышать 50 символов. Введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return

    # Определение списка недопустимых слов для фильтрации
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    # Если имя содержит любое из недопустимых слов, запрашиваем ввод повторно
    if any(bad in name.lower() for bad in banned_words):
        bot.send_message(message.chat.id, "Имя содержит недопустимые слова. Введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return

    # Получаем текущее время в формате ISO для сохранения в базе данных
    now = datetime.now().isoformat()

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Получаем идентификатор источника (chat_id) из словаря pending_users для данного пользователя
        source_id = pending_users.get(user_id, {}).get('source_chat_id')
        house_id = None

        # Если идентификатор источника существует, проверяем наличие дома в таблице houses
        if source_id:
            cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (source_id,))
            house = cursor.fetchone()
            # Если дом не найден, создаём новую запись в таблице houses
            if house is None:
                cursor.execute("INSERT INTO houses (chat_id, date_add) VALUES (?, ?)", (source_id, now))
                house_id = cursor.lastrowid
            else:
                # Если дом найден, используем его идентификатор
                house_id = house[0]

        # Проверяем, существует ли уже запись пользователя для данного дома
        if house_id is None:
            cursor.execute("SELECT id FROM users WHERE tg_id = ? AND house IS NULL", (user_id,))
        else:
            cursor.execute("SELECT id FROM users WHERE tg_id = ? AND house = ?", (user_id, house_id))
        result = cursor.fetchone()

        # Если запись не найдена, создаём новую запись с tg_id и именем
        if result is None:
            cursor.execute("INSERT INTO users (tg_id, name) VALUES (?, ?)", (user_id, name))
        else:
            # Если запись существует, обновляем имя и дату добавления
            cursor.execute("UPDATE users SET name = ?, date_add = ? WHERE id = ?", (name, now, result[0]))

        # Сохраняем изменения в базе данных
        conn.commit()
    except Exception as e:
        # Логируем ошибку и сообщаем пользователю о проблеме с сохранением данных
        logging.error(f"Ошибка при сохранении имени для пользователя {user_id}: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении данных, попробуйте позже.")
        return
    finally:
        # Закрываем соединение с базой данных
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия БД для пользователя {user_id}: {e}")

    # После успешной обработки имени переходим к запросу фамилии
    ask_surname(message.chat.id, user_id)


def ask_surname(chat_id, user_id):
    # Отправляем сообщение с запросом фамилии
    bot.send_message(chat_id, "Фамилия:")
    # Регистрируем обработчик следующего шага для обработки введённой фамилии
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_surname(message, user_id))


def process_surname(message, user_id):
    # Убираем пробелы из введённой фамилии
    surname = message.text.strip()

    # Проверяем длину фамилии; если она слишком длинная, просим ввести корректную фамилию
    if len(surname) > 50:
        bot.send_message(message.chat.id, "Фамилия не должна превышать 50 символов. Введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return

    # Проверка на наличие недопустимых слов в фамилии
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    if any(bad in surname.lower() for bad in banned_words):
        bot.send_message(message.chat.id, "Фамилия содержит недопустимые слова. Введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return

    try:
        # Подключаемся к базе данных для обновления записи пользователя
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET surname = ? WHERE tg_id = ?", (surname, user_id))
        conn.commit()
    except Exception as e:
        # Логируем ошибку и уведомляем пользователя о проблеме
        logging.error(f"Ошибка при сохранении фамилии для пользователя {user_id}: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении данных, попробуйте позже.")
        return
    finally:
        # Закрываем соединение с базой данных
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия БД для пользователя {user_id}: {e}")

    # После успешного обновления фамилии переходим к запросу номера квартиры
    ask_apartment(message.chat.id, user_id)


def ask_apartment(chat_id, user_id):
    # Отправляем сообщение с запросом номера квартиры
    bot.send_message(chat_id, "№ квартиры:")
    # Регистрируем обработчик для обработки ввода номера квартиры
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_apartment(message, user_id))


def process_apartment(message, user_id):
    """
    Обрабатывает введённый номер квартиры:
      - Проверяет, что значение является числом и находится в диапазоне от 1 до 10000.
      - Сохраняет номер квартиры в таблице users для нового дома (если пользователь регистрируется для нового дома).
      - После успешного обновления для нового дома отправляет сообщение с запросом фото и переводит состояние в "awaiting_photo".
      - Если регистрация происходит для уже существующего дома, переходит к запросу номера телефона.
    """
    # Удаляем лишние пробелы из введённого номера квартиры
    apartment_str = message.text.strip()
    try:
        # Пробуем преобразовать введённое значение в целое число
        apartment = int(apartment_str)
        # Проверяем, что номер квартиры находится в допустимом диапазоне
        if apartment < 1 or apartment > 10000:
            raise ValueError("Номер квартиры должен быть от 1 до 10000")
    except ValueError as e:
        # Если ввод некорректен, отправляем сообщение об ошибке и просим ввести данные повторно
        bot.send_message(message.chat.id, f"Ошибка: {e}. Введите номер квартиры от 1 до 10000.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_apartment(m, user_id))
        return

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Если пользователь регистрируется для нового дома, его состояние должно быть "awaiting_apartment_new_house"
        if user_state.get(user_id) == "awaiting_apartment_new_house":
            # Получаем chat_id источника регистрации
            source_chat = pending_users.get(user_id, {}).get('source_chat_id')
            # Находим последнюю запись для данного пользователя по дому NULL
            cursor.execute("SELECT MAX(id) FROM users WHERE tg_id = ? AND house IS NULL", (user_id,))
            record = cursor.fetchone()
            record_id = record[0] if record and record[0] is not None else None

            # Если запись не найдена, логируем ошибку и сообщаем пользователю
            if record_id is None:
                logging.error(f"Новая запись для пользователя {user_id} не найдена при обновлении номера квартиры для дома {source_chat}.")
                bot.send_message(message.chat.id, "Произошла ошибка при обновлении данных, попробуйте позже.")
                return

            # Обновляем номер квартиры в найденной записи
            cursor.execute("UPDATE users SET apartment = ? WHERE id = ?", (str(apartment), record_id))
        else:
            # Если дом уже существует, обновляем номер квартиры по идентификатору Telegram
            cursor.execute("UPDATE users SET apartment = ? WHERE tg_id = ?", (str(apartment), user_id))

        # Сохраняем изменения
        conn.commit()
    except Exception as e:
        # Логируем и уведомляем о возникшей ошибке
        logging.error(f"Ошибка при сохранении номера квартиры для пользователя {user_id}: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении данных, попробуйте позже.")
        return
    finally:
        # Закрываем соединение с базой данных
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия БД для пользователя {user_id}: {e}")

    # Логируем успешное сохранение номера квартиры для отладки
    logging.info(f"Пользователь {user_id}: номер квартиры '{apartment}' успешно сохранён.")

    # Если регистрация происходит для нового дома, запрашиваем отправку фотографии
    if user_state.get(user_id) == "awaiting_apartment_new_house":
        bot.send_message(message.chat.id,
                         "Отлично! Пожалуйста отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры.")
        user_state[user_id] = "awaiting_photo"
    else:
        # Иначе переходим к запросу номера телефона
        ask_phone(message.chat.id, user_id)


def ask_phone(chat_id, user_id):
    # Отправляем сообщение с запросом номера телефона в заданном формате
    bot.send_message(chat_id, "Телефон в формате +79002003030:")
    # Регистрируем обработчик следующего шага для обработки введённого номера
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_phone(message, user_id))


def process_phone(message, user_id):
    # Убираем пробелы из введённого номера телефона
    phone = message.text.strip()
    try:
        # Пытаемся распарсить номер телефона с использованием библиотеки phonenumbers
        phone_number = phonenumbers.parse(phone, None)
        # Проверяем валидность номера
        if not phonenumbers.is_valid_number(phone_number):
            raise ValueError("Номер не валидный")
        # Форматируем номер в стандартном формате E164
        formatted_phone = format_number(phone_number, PhoneNumberFormat.E164)
    except Exception as e:
        # В случае ошибки отправляем сообщение и запрашиваем ввод номера повторно
        bot.send_message(message.chat.id, f"Неверный формат телефона: {e}. Введите номер в формате +79002003030.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_phone(m, user_id))
        return
    try:
        # Подключаемся к базе данных для обновления записи пользователя
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (formatted_phone, user_id))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при сохранении телефона для пользователя {user_id}: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении данных, попробуйте позже.")
        return
    finally:
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия БД для пользователя {user_id}: {e}")

    # После успешного сохранения номера переходим к запросу информации об автомобилях
    ask_car_count(message.chat.id, user_id)


def ask_car_count(chat_id, user_id):
    # Запрашиваем у пользователя количество автомобилей
    bot.send_message(chat_id, "Укажите, сколько у вас автомобилей (0 если нет):")
    # Регистрируем обработчик для обработки введённого количества автомобилей
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_count(message, user_id))


def process_car_count(message, user_id):
    try:
        # Преобразуем введённое значение в число
        count = int(message.text.strip())
        # Проверяем, что число автомобилей находится в допустимом диапазоне от 0 до 10
        if count < 0 or count > 10:
            raise ValueError("Количество авто должно быть от 0 до 10")
    except ValueError as e:
        # В случае ошибки отправляем сообщение и запрашиваем ввод повторно
        bot.send_message(message.chat.id, f"Ошибка: {e}. Введите число от 0 до 10.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_count(m, user_id))
        return

    # Если у пользователя нет автомобилей, отправляем соответствующее сообщение и завершаем анкетирование
    if count == 0:
        bot.send_message(message.chat.id, "Понятно, вы не автомобилист!")
        finalize_questionnaire(message.chat.id, user_id)
    else:
        # Если автомобили есть, сохраняем информацию о количестве и устанавливаем текущий номер автомобиля для ввода
        user_state[user_id] = {"car_count": count, "current_car": 1}
        ask_car_number(message.chat.id, user_id)


def ask_car_number(chat_id, user_id):
    # Получаем текущий номер автомобиля, который нужно ввести
    current = user_state[user_id]["current_car"]
    # Запрашиваем у пользователя номер текущего автомобиля с примером формата
    bot.send_message(chat_id, f"Номер авто {current} (например, н001нн797):")
    # Регистрируем обработчик для обработки введённого номера автомобиля
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_number(message, user_id))


def process_car_number(message, user_id):
    # Убираем пробелы из введённого номера автомобиля
    autonum = message.text.strip()
    # Проверяем, что длина номера автомобиля в допустимом диапазоне
    if len(autonum) < 3 or len(autonum) > 15:
        bot.send_message(message.chat.id, "Номер авто должен содержать от 3 до 15 символов. Введите корректный номер.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_number(m, user_id))
        return

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # Получаем запись пользователя по tg_id
        cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
        user_record = cursor.fetchone()
        if user_record:
            # Вставляем новую запись в таблицу cars с данными о номере автомобиля, оставляя date_add равным NULL
            cursor.execute("INSERT INTO cars (user, autonum) VALUES (?, ?)", (user_record[0], autonum))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при сохранении номера авто для пользователя {user_id}: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка при сохранении данных, попробуйте позже.")
        return
    finally:
        # Закрываем соединение с базой данных
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия БД для пользователя {user_id}: {e}")

    # Увеличиваем счётчик введённых автомобилей
    user_state[user_id]["current_car"] += 1
    # Если еще остались автомобили для ввода, запрашиваем следующий номер, иначе завершаем анкетирование
    if user_state[user_id]["current_car"] <= user_state[user_id]["car_count"]:
        ask_car_number(message.chat.id, user_id)
    else:
        finalize_questionnaire(message.chat.id, user_id)


def finalize_questionnaire(chat_id, user_id):
    # Отправляем сообщение, что анкета заполнена, и просим отправить фото дворовой территории
    bot.send_message(chat_id, "Анкета заполнена. Теперь отправьте актуальное фото дворовой территории из окна вашей квартиры.")
    # Обновляем состояние пользователя, переводя его в режим ожидания фото
    user_state[user_id] = "awaiting_photo"