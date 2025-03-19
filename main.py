"""
ResidentChatBot main module 88
============================
Этот модуль реализует Telegram-бота для управления процессом регистрации и идентификации жильцов.
Бот обрабатывает команды, новые входы в чат, идентификацию посредством отправки фото, а также проводит опрос для регистрации.
Конфигурация загружается из файла .env, а данные сохраняются в SQLite базе данных.
"""

import telebot
import logging
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
import os
from dotenv import load_dotenv
import sqlite3
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, format_number

# Загрузка переменных окружения из файла .env и присвоение их соответствующим переменным
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")
BOT_NAME = os.getenv("BOT_NAME")

# Настройка логирования: вывод времени, уровня логирования и сообщения
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Глобальные словари для отслеживания состояния пользователей и соответствия админа и пользователя
admin_to_user_map = {}
user_state = {}  # Состояния диалога в личном чате, ключ – tg_id

# Инициализация SQLite базы данных и создание необходимых таблиц, если они отсутствуют
# Таблицы: groups, houses, users, cars
conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS houses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        house_name TEXT,
        chat_id INTEGER UNIQUE,
        house_city TEXT,
        house_address TEXT,
        date_add TEXT,
        date_del TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        name TEXT,
        surname TEXT,
        house INTEGER,
        apartment TEXT,
        phone TEXT,
        date_add TEXT,
        date_del TEXT,
        FOREIGN KEY(house) REFERENCES houses(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user INTEGER,
        autonum TEXT,
        date_add TEXT,
        date_del TEXT,
        FOREIGN KEY(user) REFERENCES users(id)
    )
''')
conn.commit()
conn.close()

# Проверка обязательных переменных окружения. Если API_TOKEN или ADMIN_ID не заданы, генерируется исключение
if not API_TOKEN or not ADMIN_ID:
    raise ValueError("API_TOKEN и ADMIN_ID должны быть указаны в .env")

# Инициализация Telegram-бота с использованием API_TOKEN
bot = telebot.TeleBot(API_TOKEN)
pending_users = {}  # Словарь для отслеживания новых участников
group_id = None     # Переменная для хранения ID текущей группы
source_chat_id = None  # Переменная для хранения исходного chat_id

# -------------------- Обработчики команд и callback --------------------

# Обработчик команды /start в личном чате.
# Отправляет приветственное сообщение с кнопкой для начала процедуры знакомства.
@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.chat.type != 'private':
        return  # /start обрабатывается только в личном чате
    user_first_name = f"@{message.from_user.first_name}" if message.from_user.first_name else "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    intro_button = InlineKeyboardButton("Познакомиться", callback_data="start_introduction")
    keyboard.add(intro_button)
    bot.send_message(message.chat.id,
        f"Привет, {user_first_name}! Я бот чата жильцов. Закрытый чат жителей. Для участия нужно познакомиться и пройти идентификацию. Это займёт 2 минуты.",
        reply_markup=keyboard)

# Callback-обработчик для кнопки \"Познакомиться\".
# Устанавливает состояние пользователя на 'awaiting_confirm' и предлагает варианты подтверждения проживания.
@bot.callback_query_handler(func=lambda call: call.data == "start_introduction")
def start_introduction_handler(call):
    user_id = call.from_user.id
    # Проверяем наличие пользователя в базе данных
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, date_del FROM users WHERE tg_id = ?", (user_id,))
    user_record = cursor.fetchone()
    conn.close()

    if user_record:
        # Если пользователь существует
        if user_record[2] and user_record[2].strip() != "":
            # Если запись помечена как удалённая (date_del заполнено), предлагаем вернуться в группу
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id, f"Привет {('@' + user_record[1]) if user_record[1] and user_record[1] != 'None' else ''}! Хотите вернуться в группу?", reply_markup=keyboard)
        else:
            # Если пользователь уже активен
            bot.send_message(call.message.chat.id, f"{('@' + user_record[1]) if user_record[1] and user_record[1] != 'None' else ''}, мы тебя узнали и ты уже зарегистрирован.")
        bot.answer_callback_query(call.id)
        return

    # Если пользователь не найден в базе, продолжаем обычную процедуру знакомства
    user_state[user_id] = "awaiting_confirm"
    keyboard = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)
    bot.send_message(call.message.chat.id, "Пожалуйста, подтвердите ваше проживание:", reply_markup=keyboard)
    bot.answer_callback_query(call.id)

# Обработчик новых участников в группе.
# Ограничивает возможность отправки сообщений новым участникам и предлагает пройти процедуру знакомства.
@bot.message_handler(content_types=['new_chat_members'])
def new_member_handler(message):
    global group_id
    group_id = message.chat.id  # Обновляем ID группы
    for new_member in message.new_chat_members:
        if new_member.id not in pending_users or pending_users[new_member.id]['status'] in ['approved', 'left']:
            pending_users[new_member.id] = {
                'status': 'awaiting_photo',
                'join_time': datetime.now(),
                'source_chat_id': group_id  # Сохраняем chat_id источника
            }
            if new_member.id != bot.get_me().id:
                try:
                    bot.restrict_chat_member(group_id, new_member.id, can_send_messages=False)
                except telebot.apihelper.ApiTelegramException as e:
                    logging.error(f"Ошибка ограничения для пользователя {new_member.id}: {e}")
            keyboard = InlineKeyboardMarkup(row_width=1)
            access_button = InlineKeyboardButton("Получить доступ", url=f"https://t.me/{BOT_NAME}?start")
            keyboard.add(access_button)
            bot.send_message(group_id,
                f"Добро пожаловать, {new_member.first_name}! Чтобы получить доступ к чату, пожалуйста, пройдите процедуру знакомства и подтверждения. Чтобы получить доступ, нажмите кнопку ниже.",
                reply_markup=keyboard)
# Обработчик фото для идентификации.
# Если бот ожидает фото, пересылает фото администратору с кнопками для действий (разрешить, отклонить, запросить новое фото)
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    user_id = message.from_user.id
    if user_state.get(user_id) == "awaiting_photo":
        if user_id == bot.get_me().id:
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        else:
            # Извлекаем информацию о пользователе из базы данных
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name, surname, apartment, phone FROM users WHERE tg_id = ?", (user_id,))
            user_info = cursor.fetchone()
            conn.close()
            if user_info:
                name, surname, apartment, phone = user_info
            else:
                name = message.from_user.first_name
                surname = ""
                apartment = "не указана"
                phone = "не указан"

            # Получаем информацию о чате (группе) из pending_users или используем group_id
            source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
            try:
                group = bot.get_chat(source_chat_id)
                group_title = group.title if group.title else group.username
            except Exception as e:
                logging.error(f"Ошибка получения информации о чате: {e}")
                group_title = "Неизвестный чат"

            # Формируем сообщение для администратора с информацией о пользователе
            registration_info = (
                f"Новый пользователь {('@' + message.from_user.first_name) if message.from_user.first_name and message.from_user.first_name != 'None' else message.from_user.first_name} (id: {user_id}) подал запрос на регистрацию в чате {('@' + group_title) if group_title and group_title != 'None' else group_title} (id: {source_chat_id}).\n"
                f"Имя: {name}\n"
                f"Фамилия: {surname}\n"
                f"Квартира: {apartment}\n"
                f"Телефон: {phone}"
            )

            # Создаем клавиатуру с тремя кнопками
            keyboard = InlineKeyboardMarkup(row_width=1)
            allow_button = InlineKeyboardButton("Дать доступ", callback_data=f"allow:{user_id}")
            deny_button = InlineKeyboardButton("Отклонить доступ", callback_data=f"deny:{user_id}")
            request_photo_button = InlineKeyboardButton("Запросить новое фото", callback_data=f"request_photo:{user_id}")
            keyboard.add(allow_button, deny_button, request_photo_button)

            # Отправляем сообщение с информацией и фото администратору
            bot.send_message(ADMIN_ID, registration_info)
            bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, reply_markup=keyboard)
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        user_state[user_id] = "photo_sent"
    else:
        bot.send_message(message.chat.id, "Напоминаю, что я жду от вас фото для идентификации.")

# Callback-обработчик для разрешения доступа пользователю.
# Снимает ограничения с пользователя, обновляет статус и отправляет уведомления пользователю и администратору.
@bot.callback_query_handler(func=lambda call: call.data.startswith("allow:"))
def allow_access(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(f"Перед обработкой кнопки 'Дать доступ' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")
    if source_chat_id:
        member = None
        try:
            member = bot.get_chat_member(source_chat_id, user_id)
            if member.status not in ['left', 'kicked']:
                logging.info(f"Текущий пользователь {user_id} в исходном чате {source_chat_id} найден!")
        except Exception as e:
            logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
        if source_chat_id:
            try:
                bot.restrict_chat_member(source_chat_id, user_id, can_send_messages=True)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f"Ошибка снятия ограничений для пользователя {user_id} в чате {source_chat_id}: {e}")
        else:
            logging.error(f"Пользователь {user_id} не найден ни в одном известном чате.")
        if user_id not in pending_users:
            pending_users[user_id] = {
                'status': 'awaiting_photo',
                'join_time': datetime.now()
            }
        pending_users[user_id]['status'] = 'approved'
        logging.info("Доступ открыт")
        bot.send_message(user_id, f"Доступ разрешён и вы можете воспользоваться всеми возможностями группы жильцов" +
            (f" (@{bot.get_chat(source_chat_id).username})" if bot.get_chat(source_chat_id).username else "") + ".")
        bot.send_message(source_chat_id, f"Приветствуем пользователя {('@' + member.user.first_name) if member.user.first_name and member.user.first_name != 'None' else member.user.first_name}" +
                         (f" (@{member.user.username})" if member.user.username else ". Он получает доступ ко всем возможностями группы. Поздравляем!"))
        logging.info(f"call.id: {call.id}")
        bot.answer_callback_query(call.id, "Доступ предоставлен.")
        bot.send_message(chat_id=ADMIN_ID, text=f"Доступ пользователю {('@' + member.user.first_name) if member.user.first_name and member.user.first_name != 'None' else member.user.first_name}" +
                              (f" (@{member.user.username})" if member.user.username else "") + " предоставлен.")
    else:
        bot.send_message(user_id, f"Группа не определена ({source_chat_id})!\nОшибка снятия ограничений для пользователя {user_id}!")

# Callback-обработчик для отклонения доступа пользователю.
# Удаляет пользователя из чата, обновляет статус и отправляет уведомления.
@bot.callback_query_handler(func=lambda call: call.data.startswith("deny:"))
def deny_access(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(f"Перед обработкой кнопки 'Отклонить доступ' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")
    member = None
    try:
        member = bot.get_chat_member(source_chat_id, user_id)
        if member.status not in ['left', 'kicked']:
            logging.info(f"Текущий пользователь {user_id} в исходном чате {source_chat_id} найден!")
    except Exception as e:
        logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
    if source_chat_id:
        try:
            bot.kick_chat_member(source_chat_id, user_id)
            bot.unban_chat_member(source_chat_id, user_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка отклонения запроса и удаления пользователя {user_id} из чата {source_chat_id}: {e}")
    else:
        logging.error(f"Пользователь {user_id} не найден ни в одном известном чате.")
    logging.info("Доступ ОТКЛОНЁН и пользователь УДАЛЁН")
    bot.send_message(user_id, f"Ваш запрос отклонён, потому что вы прислали не релевантное фото. Напоминаю, что следовало прислать фото вида из окна вашей квартиры, которое вы сделали сегодня.")
    bot.send_message(source_chat_id, f"Пользователю {member.user.first_name}" +
        (f" ({member.user.username})" if member.user.username else " доступ не предоставлен и он удалён за предоставление не релевантной фотографии."))
    logging.info(f"call.id: {call.id}")
    bot.answer_callback_query(call.id, "Доступ отклонён!")
    bot.send_message(chat_id=ADMIN_ID, text=f"Доступ пользователю {member.user.first_name}" +
        (f" (@{member.user.username})" if member.user.username else "") + f" ОТКЛОНЁН и он УДАЛЁН из группы ({source_chat_id}).")

# Callback-обработчик для запроса нового фото.
# Отправляет администратору сообщение с просьбой указать причину запроса нового фото.
@bot.callback_query_handler(func=lambda call: call.data.startswith("request_photo:"))
def request_photo(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(f"Перед обработкой кнопки 'Запросить новое фото' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")
    admin_to_user_map[ADMIN_ID] = user_id
    request_reason = f"Пожалуйста, укажите причину для запроса нового фото от @{user_id}."
    bot.send_message(ADMIN_ID, request_reason)

# Обработчик сообщений от администратора (ADMIN_ID).
# Сохраняет причину запроса нового фото, уведомляет администратора и пересылает запрос пользователю.
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID)
def save_reason(message):
    global group_id
    user_id = admin_to_user_map.get(ADMIN_ID)
    if user_id is not None:
        pending_users[user_id]['reason'] = message.text
        bot.send_message(ADMIN_ID, "Причина сохранена.")
        reason = pending_users[user_id].get('reason', "причина не указана")
        bot.send_message(user_id, f"Требуется новое фото по причине: {reason}")
        bot.send_message(pending_users[user_id]['source_chat_id'], f"@{user_id} требуется уточнение. Запрос отправлен личным сообщением от чатбота.")
    else:
        bot.send_message(ADMIN_ID, "Не найден user_id для ADMIN_ID.")

# Обработчик события выхода участника из чата.
# Обновляет записи в базе данных, помечая пользователя и его транспорт как удалённые.
@bot.message_handler(content_types=['left_chat_member'])
def left_member_handler(message):
    left_user = message.left_chat_member
    user_id = left_user.id
    now = datetime.now().isoformat()
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET date_del = ? WHERE tg_id = ?", (now, user_id))
        cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
        user_record = cursor.fetchone()
        if user_record:
            cursor.execute("UPDATE cars SET date_del = ? WHERE user = ? AND (date_del IS NULL OR date_del = '')", (now, user_record[0]))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при обработке выхода пользователя {user_id}: {e}")
    finally:
        try:
            conn.close()
        except Exception as e:
            logging.error(f"Ошибка закрытия соединения с БД для пользователя {user_id}: {e}")
    if user_id in pending_users:
        del pending_users[user_id]

# Callback-обработчик для идентификации.
# Отправляет клавиатуру для подтверждения проживания и логирует информацию о группе.
@bot.callback_query_handler(func=lambda call: call.data == 'identification')
def identification_handler(call):
    global group_id, source_chat_id
    if call.message.chat is None:
        logging.error("call.message.chat is None, cannot process identification.")
        return
    user_id = call.from_user.id
    if user_id in pending_users:
        source_chat_id = pending_users[user_id]['source_chat_id']
    logging.info(f"Обработчик вызван для группы {source_chat_id} (ID: {call.message.chat.id})")
    keyboard = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)
    bot.send_message(call.message.chat.id, "Пожалуйста, подтвердите ваше проживание:", reply_markup=keyboard)
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM groups")
    group_ids = cursor.fetchall()
    logging.info(f"Group IDs: {group_ids}")
    conn.close()

# Callback-обработчик для пользователей, которые подтверждают, что не являются жильцами.
# Информирует пользователя и удаляет его из чата.
@bot.callback_query_handler(func=lambda call: call.data == "not_residing")
def not_residing_handler(call):
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Чат предназначен только для жильцов.")
    source_id = pending_users.get(user_id, {}).get('source_chat_id')
    now = datetime.now().isoformat()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET date_del = ? WHERE tg_id = ?", (now, user_id))
    cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
    user_record = cursor.fetchone()
    if user_record:
        cursor.execute("UPDATE cars SET date_del = ? WHERE user = ? AND (date_del IS NULL OR date_del = '')", (now, user_record[0]))
    conn.commit()
    conn.close()
    if source_id:
        try:
            bot.kick_chat_member(source_id, user_id)
            bot.unban_chat_member(source_id, user_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка удаления пользователя {user_id} из чата {source_id}: {e}")
    bot.answer_callback_query(call.id)

# Callback-обработчик для выбора опции "Да" при возвращении в группу.
@bot.callback_query_handler(func=lambda call: call.data == "return_yes")
def return_yes_handler(call):
    user_id = call.from_user.id
    now = datetime.now().isoformat()
    # Обновляем запись: очищаем поле date_del и обновляем дату регистрации
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET date_del = NULL, date_add = ? WHERE tg_id = ?", (now, user_id))
    conn.commit()
    conn.close()
    bot.send_message(call.message.chat.id, "Отлично! Пожалуйста, отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры.")
    user_state[user_id] = "awaiting_photo"
    bot.answer_callback_query(call.id)

# Callback-обработчик для выбора опции "Нет" при возвращении в группу.
@bot.callback_query_handler(func=lambda call: call.data == "return_no")
def return_no_handler(call):
    bot.send_message(call.message.chat.id, "Ну, заходи если чё...")
    bot.answer_callback_query(call.id)

# Callback-обработчик для подтверждения проживания.
# Проверяет, зарегистрирован ли пользователь ранее, и запускает процедуру заполнения анкеты, если необходимо.
@bot.callback_query_handler(func=lambda call: call.data == "confirm_residence")
def confirm_residence_handler(call):
    user_id = call.from_user.id
    # Подключаемся к базе данных и проверяем наличие пользователя по tg_id
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, date_del FROM users WHERE tg_id = ?", (user_id,))
    user_record = cursor.fetchone()

    if user_record:
        # Если пользователь найден и активен (date_del пустое) – сообщаем, что он уже зарегистрирован
        if not user_record[2] or user_record[2].strip() == "":
            bot.send_message(call.message.chat.id, f"{user_record[1]}, мы тебя узнали и ты уже зарегистрирован.")
            conn.close()
            bot.answer_callback_query(call.id)
            return
        else:
            # Если запись была удалена (date_del заполнено) – предлагаем вернуть пользователя в группу
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id, f"Привет {user_record[1]}! Хотите вернуться в группу?", reply_markup=keyboard)
            conn.close()
            bot.answer_callback_query(call.id)
            return

    conn.close()
    # Если записи нет, начинаем процедуру заполнения анкеты
    bot.send_message(call.message.chat.id, "Ответьте на несколько вопросов, пожалуйста. Данные на серверах хранятся в зашифрованном виде в соответствии с требованиями регулятора.")
    ask_name(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id)

# -------------------- Функции для проведения опроса (анкеты) --------------------

# Запрос имени пользователя
def ask_name(chat_id, user_id):
    bot.send_message(chat_id, "Ваше имя:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_name(message, user_id))

# Обработка введённого имени и сохранение в базе данных
def process_name(message, user_id):
    name = message.text.strip()
    # Проверка: имя должно быть не длиннее 50 символов
    if len(name) > 50:
        bot.send_message(message.chat.id, "Имя не должно превышать 50 символов. Пожалуйста, введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return
    # Фильтрация запрещённых слов (пример: 'бляд', 'хуй', 'пизд', 'сука')
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    if any(bad in name.lower() for bad in banned_words):
        bot.send_message(message.chat.id, "Имя содержит недопустимые слова. Пожалуйста, введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return

    # Если имеется справочник имён, здесь можно добавить проверку на корректность имени

    now = datetime.now().isoformat()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
    result = cursor.fetchone()
    if result is None:
        source_id = pending_users.get(user_id, {}).get('source_chat_id')
        house_id = None
        if source_id:
            cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (source_id,))
            house = cursor.fetchone()
            if house is None:
                cursor.execute("INSERT INTO houses (chat_id, date_add) VALUES (?, ?)", (source_id, now))
                house_id = cursor.lastrowid
            else:
                house_id = house[0]
        cursor.execute("INSERT INTO users (tg_id, name, house, date_add) VALUES (?, ?, ?, ?)",
                       (user_id, name, house_id, now))
    else:
        cursor.execute("UPDATE users SET name = ?, date_add = ? WHERE tg_id = ?", (name, now, user_id))
    conn.commit()
    conn.close()
    ask_surname(message.chat.id, user_id)

# Запрос фамилии пользователя
def ask_surname(chat_id, user_id):
    bot.send_message(chat_id, "Фамилия:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_surname(message, user_id))

# Обработка введённой фамилии и сохранение в базе данных
def process_surname(message, user_id):
    surname = message.text.strip()
    # Проверка: фамилия не должна превышать 50 символов
    if len(surname) > 50:
        bot.send_message(message.chat.id,
                         "Фамилия не должна превышать 50 символов. Пожалуйста, введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return
    # Фильтрация запрещённых слов
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    if any(bad in surname.lower() for bad in banned_words):
        bot.send_message(message.chat.id,
                         "Фамилия содержит недопустимые слова. Пожалуйста, введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET surname = ? WHERE tg_id = ?", (surname, user_id))
    conn.commit()
    conn.close()
    ask_apartment(message.chat.id, user_id)

# Запрос номера квартиры
def ask_apartment(chat_id, user_id):
    bot.send_message(chat_id, "№ квартиры:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_apartment(message, user_id))

# Обработка номера квартиры и сохранение в базе данных
def process_apartment(message, user_id):
    apartment_str = message.text.strip()
    try:
        apartment = int(apartment_str)
        if apartment < 1 or apartment > 10000:
            raise ValueError("Номер квартиры должен быть от 1 до 10000")
    except ValueError as e:
        bot.send_message(message.chat.id,
                         f"Ошибка: {e}. Пожалуйста, введите номер квартиры в виде целого числа от 1 до 10000.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_apartment(m, user_id))
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET apartment = ? WHERE tg_id = ?", (str(apartment), user_id))
    conn.commit()
    conn.close()
    ask_phone(message.chat.id, user_id)

# Запрос телефона пользователя
def ask_phone(chat_id, user_id):
    bot.send_message(chat_id, "Телефон в формате +79002003030:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_phone(message, user_id))

# Обработка телефона и сохранение в базе данных
def process_phone(message, user_id):
    phone = message.text.strip()
    try:
        # Attempt to parse the phone number; since it should include a '+' and country code, pass None as region
        phone_number = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(phone_number):
            raise ValueError("Номер не валидный")
        # Format the number to E164 standard (e.g., +79002003030)
        formatted_phone = format_number(phone_number, PhoneNumberFormat.E164)
    except Exception as e:
        error_message = (
            f"Неверный формат телефона: {e}\n"
            "Пожалуйста, введите номер в формате +79002003030.\n"
            "Если проблемы сохраняются, свяжитесь с администратором: @proskurninra"
        )
        bot.send_message(message.chat.id, error_message)
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_phone(m, user_id))
        return

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (formatted_phone, user_id))
    conn.commit()
    conn.close()
    ask_car_count(message.chat.id, user_id)

# Запрос количества автомобилей для помощи автомобилистам
def ask_car_count(chat_id, user_id):
    bot.send_message(chat_id, "Для помощи автомобилистам укажите сколько у вас автомобилей. Если машин нет, то укажите 0:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_count(message, user_id))

# Обработка количества автомобилей и переход к вводу номера автомобиля, если требуется
def process_car_count(message, user_id):
    try:
        count = int(message.text.strip())
        if count < 0 or count > 10:
            raise ValueError("Количество авто должно быть от 0 до 10")
    except ValueError as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}. Пожалуйста, введите целое число от 0 до 10.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_count(m, user_id))
        return

    if count == 0:
        bot.send_message(message.chat.id, "Понял, вы не автомобилист!")
        finalize_questionnaire(message.chat.id, user_id)
    else:
        user_state[user_id] = {"car_count": count, "current_car": 1}
        ask_car_number(message.chat.id, user_id)

# Запрос номера автомобиля
def ask_car_number(chat_id, user_id):
    current = user_state[user_id]["current_car"]
    bot.send_message(chat_id, f"Номер авто {current} в формате н001нн797 (буквы русские):")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_number(message, user_id))

# Обработка номера автомобиля и сохранение в базе данных
def process_car_number(message, user_id):
    autonum = message.text.strip()
    # Проверка: номер авто должен быть строкой от 3 до 15 символов
    if len(autonum) < 3 or len(autonum) > 15:
        bot.send_message(message.chat.id,
                         "Номер авто должен содержать от 3 до 15 символов. Пожалуйста, введите корректный номер авто.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_number(m, user_id))
        return

    # Здесь можно добавить проверку формата номера авто по справочнику (если есть)

    now = datetime.now().isoformat()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
    user_record = cursor.fetchone()
    if user_record:
        cursor.execute("INSERT INTO cars (user, autonum, date_add) VALUES (?, ?, ?)", (user_record[0], autonum, now))
    conn.commit()
    conn.close()
    user_state[user_id]["current_car"] += 1
    if user_state[user_id]["current_car"] <= user_state[user_id]["car_count"]:
        ask_car_number(message.chat.id, user_id)
    else:
        finalize_questionnaire(message.chat.id, user_id)

# Завершение анкеты и перевод пользователя в состояние ожидания фото для подтверждения актуальности
def finalize_questionnaire(chat_id, user_id):
    bot.send_message(chat_id, "Спасибо, анкета заполнена. Теперь, пожалуйста, отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры. Фотография будет сверяться с фактической обстановкой модераторами. Если Вы хотите воспользоваться подтверждением по документам, сообщите это администратору @proskurninra личным сообщением.")
    user_state[user_id] = "awaiting_photo"

# Обработчик команды /db для администратора.
# Выводит содержимое таблиц базы данных (houses, users, cars). Доступ разрешён только администратору.
@bot.message_handler(commands=['db'])
def db_handler(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа")
        return
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    output = "Таблица houses\n"
    output += " id | house_name | chat_id | house_city | house_address \n"
    cursor.execute("SELECT * FROM houses")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    output += "\nТаблица users\n"
    output += " id | tg_id | name | surname | house | apartment | phone \n"
    cursor.execute("SELECT * FROM users")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    output += "\nТаблица cars\n"
    output += " id | user | autonum \n"
    cursor.execute("SELECT * FROM cars")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    conn.close()
    bot.send_message(message.chat.id, output)

# -------------------- Запуск бота --------------------
# Запуск цикла опроса для получения обновлений от Telegram
bot.polling()