"""ResidentChatBot main module
============================
Этот модуль реализует Telegram-бота для управления процессом регистрации и идентификации жильцов.
Бот обрабатывает команды, новые входы в чат, идентификацию посредством отправки фото, а также проводит опрос для регистрации.
Конфигурация загружается из файла .env, а данные сохраняются в SQLite базе данных.
"""

# Импорт необходимых библиотек
import telebot  # Библиотека для работы с Telegram Bot API
import logging  # Для логирования работы бота
from datetime import datetime, timedelta  # Для работы с датой и временем
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
import os  # Для работы с файловой системой
# Определяем абсолютный путь к директории скрипта и к файлу базы данных
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.db")

from dotenv import load_dotenv  # Для загрузки переменных окружения из файла .env
import sqlite3  # Для работы с SQLite базой данных
import phonenumbers  # Для валидации номеров телефонов
from phonenumbers import NumberParseException, PhoneNumberFormat, format_number

# Загружаем переменные окружения из файла .env
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # (не используется в коде, но может пригодиться)
# ADMIN_ID задается как целое число
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_NAME = os.getenv("BOT_NAME")

# Настройка логирования: выводим время, уровень логирования и сообщение
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Глобальные словари для отслеживания состояния пользователей и администратора:
admin_to_user_map = {}  # Пока не используется, но можно использовать для маппинга администратора и пользователя
user_state = {}         # Состояние диалога в личном чате (ключ – tg_id пользователя)
admin_state = {}        # Состояние администратора при запросе новой фотографии

# Создание и инициализация базы данных:
# Подключаемся к базе данных (если файла нет, SQLite создаст его)
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Создаем таблицу groups, если она не существует
cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY
    )
''')

# Создаем таблицу houses для хранения информации о домах (групповых чатах)
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

# Создаем таблицу users для хранения информации о пользователях.
# Здесь используется составное уникальное ограничение (tg_id, house) – один пользователь может быть зарегистрирован в разных домах.
cursor.execute('''
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
''')

# Создаем таблицу cars для хранения информации об автомобилях пользователей.
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

# Проверка, что обязательные переменные окружения заданы, иначе генерируем ошибку
if not API_TOKEN or not ADMIN_ID:
    raise ValueError("API_TOKEN и ADMIN_ID должны быть указаны в .env")

# Инициализируем бота с использованием API_TOKEN
bot = telebot.TeleBot(API_TOKEN)

# Словарь pending_users для отслеживания новых участников: хранит их статус, время вступления и исходный чат
pending_users = {}
group_id = None         # Переменная для хранения ID текущей группы (используется в некоторых местах)
source_chat_id = None   # Переменная для хранения исходного chat_id (используется для регистрации)

# ======================================================
# Функция для определения исходного чата (source_chat_id) для пользователя
def get_source_chat_id(user_id):
    """
    Функция ищет в базе данных информацию о домах (чатах), где зарегистрирован пользователь.
    Если найден ровно один дом, возвращает его chat_id и сохраняет в pending_users.
    Если найдено несколько домов, отправляет админу сообщение для выбора.
    Если дом не найден, возвращает None.
    """
    if user_id in pending_users and pending_users[user_id].get('source_chat_id'):
        return pending_users[user_id]['source_chat_id']
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
      SELECT h.chat_id, h.house_name FROM houses h
      JOIN users u ON u.house = h.id
      WHERE u.tg_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    if len(rows) == 1:
         pending_users[user_id] = pending_users.get(user_id, {})
         pending_users[user_id]['source_chat_id'] = rows[0][0]
         return rows[0][0]
    elif len(rows) > 1:
         # Если найдено несколько домов, просим администратора выбрать нужный
         keyboard = InlineKeyboardMarkup(row_width=1)
         for chat, house_name in rows:
              button_text = f"{house_name} ({chat})" if house_name else f"Чат {chat}"
              button = InlineKeyboardButton(button_text, callback_data=f"choose_source:{user_id}:{chat}")
              keyboard.add(button)
         bot.send_message(ADMIN_ID, f"Выберите чат пользователя с id {user_id}", reply_markup=keyboard)
         return None
    else:
         return None

# Callback-обработчик для выбора исходного чата администратором
@bot.callback_query_handler(func=lambda call: call.data.startswith("choose_source:"))
def choose_source_handler(call):
    parts = call.data.split(":")
    if len(parts) == 3:
         user_id = int(parts[1])
         chosen_chat_id = parts[2]
         if user_id not in pending_users:
              pending_users[user_id] = {}
         pending_users[user_id]['source_chat_id'] = chosen_chat_id
         bot.answer_callback_query(call.id, "Чат выбран.")
         bot.send_message(ADMIN_ID, f"Для пользователя {user_id} выбран чат {chosen_chat_id}.")

# ======================================================
# Обработчик команды /start в личном чате бота
@bot.message_handler(commands=['start'])
def start_handler(message):
    # Обрабатываем /start только в приватном чате
    if message.chat.type != 'private':
        return
    user_first_name = f"@{message.from_user.first_name}" if message.from_user.first_name else "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    # Кнопка для начала знакомства
    intro_button = InlineKeyboardButton("Познакомиться", callback_data="start_introduction")
    keyboard.add(intro_button)
    bot.send_message(message.chat.id,
        f"Привет, {user_first_name}! Я бот чата жильцов. Закрытый чат жителей. Для участия нужно познакомиться и пройти идентификацию. Это займёт 2 минуты.",
        reply_markup=keyboard)

# Callback-обработчик для кнопки "Познакомиться"
@bot.callback_query_handler(func=lambda call: call.data == "start_introduction")
def start_introduction_handler(call):
    """
    Обработчик кнопки "Познакомиться".
    Определяет исходный групповой чат, откуда пришёл пользователь, и проверяет, зарегистрирован ли он для этого дома.
    Если пользователь уже зарегистрирован для данного дома, отправляет стандартное сообщение.
    Если пользователь есть в базе, но не зарегистрирован для текущего дома, регистрирует его для нового дома
    и отправляет сообщение с просьбой прислать фото для подтверждения регистрации.
    Если пользователь новый, запускается полный процесс регистрации (опрос).
    """
    user_id = call.from_user.id
    user_first_name = f"@{call.from_user.first_name}" if call.from_user.first_name else "сосед"
    # Определяем, откуда пришёл пользователь: если вызов из приватного чата – берем сохранённый source_chat_id, иначе используем текущий chat.id
    if call.message.chat.type == "private" and user_id in pending_users and pending_users[user_id].get('source_chat_id'):
         current_source_chat = pending_users[user_id]['source_chat_id']
    else:
         current_source_chat = call.message.chat.id

    # Сохраняем или обновляем исходный чат для пользователя
    db_source = get_source_chat_id(user_id)
    if db_source is None or db_source != current_source_chat:
         source_chat = current_source_chat
         pending_users[user_id] = pending_users.get(user_id, {})
         pending_users[user_id]['source_chat_id'] = current_source_chat
    else:
         source_chat = db_source

    # Определяем, существует ли дом (chat) в таблице houses, используя исходный чат
    house_id = None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (source_chat,))
    house_row = cursor.fetchone()
    if house_row:
        house_id = house_row[0]
    # Проверяем, зарегистрирован ли пользователь для данного дома (source_chat)
    cursor.execute("SELECT id, name, date_del FROM users WHERE tg_id = ? AND house = ?", (user_id, house_id))
    user_record = cursor.fetchone()
    conn.close()

    if user_record:
        # Если пользователь зарегистрирован, отправляем стандартное сообщение
        if user_record[2] and user_record[2].strip() != "":
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id,
                             f"А мы вас знаем {user_first_name}! Хотите вернуться в группу?",
                             reply_markup=keyboard)
        else:
            bot.send_message(call.message.chat.id,
                             f"{('@' + user_record[1]) if user_record[1] and user_record[1] != 'None' else ''}, мы тебя узнали и ты уже зарегистрирован.")
        bot.answer_callback_query(call.id)
        return
    else:
        # Если пользователь есть в базе, но не зарегистрирован для текущего (исходного) чата
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
        existing = cursor.fetchone()
        conn.close()
        if existing:
            # Регистрируем пользователя для нового дома
            now = datetime.now().isoformat()
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (tg_id, name, house, date_add) VALUES (?, ?, ?, ?)",
                           (user_id, call.from_user.first_name, house_id, now))
            conn.commit()
            conn.close()
            user_state[user_id] = "awaiting_photo"
            # Отправляем сообщение именно в исходном чате (source_chat), откуда пользователь пришёл
            bot.send_message(source_chat,
                             f"Привет {user_first_name}! Ты регистрируешься из нового дома {source_chat}. Пришли фото из квартиры для подтверждения регистрации.")
            bot.answer_callback_query(call.id)
            return
        else:
            # Если пользователь новый – запускаем полный процесс регистрации (опрос)
            ask_name(call.message.chat.id, user_id)
            bot.answer_callback_query(call.id)
            return

# Обработчик новых участников в группе
@bot.message_handler(content_types=['new_chat_members'])
def new_member_handler(message):
    logging.info("new_member_handler вызван")
    chat_id = message.chat.id  # Текущий групповой чат
    # Проверяем, существует ли запись о данном чате в таблице houses
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (chat_id,))
    house_record = cursor.fetchone()
    if house_record is None:
        # Если группа (дом) еще не занесена в базу, создаем запись
        now = datetime.now().isoformat()
        cursor.execute("INSERT INTO houses (chat_id, date_add) VALUES (?, ?)", (chat_id, now))
        conn.commit()
    conn.close()

    # Для каждого нового участника сохраняем его данные и отправляем сообщение с кнопкой "Получить доступ"
    for new_member in message.new_chat_members:
        pending_users[new_member.id] = {
            'status': 'awaiting_photo',
            'join_time': datetime.now(),
            'source_chat_id': chat_id  # Сохраняем исходный групповой чат
        }
        if new_member.id != bot.get_me().id:
            try:
                # Ограничиваем возможность отправки сообщений (предварительно)
                bot.restrict_chat_member(chat_id, new_member.id, can_send_messages=False)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f"Ошибка ограничения для пользователя {new_member.id}: {e}")
            keyboard = InlineKeyboardMarkup(row_width=1)
            access_button = InlineKeyboardButton("Получить доступ", url=f"https://t.me/{BOT_NAME}?start")
            keyboard.add(access_button)
            bot.send_message(chat_id,
                f"Добро пожаловать, @{new_member.first_name}! Чтобы получить доступ к чату, пройдите процедуру знакомства и подтверждения. Нажмите кнопку ниже.",
                reply_markup=keyboard)

# Обработчик фотографий для идентификации
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    user_id = message.from_user.id
    # Обрабатываем, если состояние пользователя соответствует ожиданию фото
    if user_state.get(user_id) in ["awaiting_photo", "awaiting_new_photo"]:
        if user_id == bot.get_me().id:
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        else:
            # Получаем информацию о пользователе из базы
            conn = sqlite3.connect(DB_FILE)
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

            # Определяем исходный групповой чат для данного пользователя
            source_chat_id = get_source_chat_id(user_id)
            if source_chat_id is None:
                bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
                return

            # Пытаемся получить данные о чате (для вывода имени чата)
            try:
                group = bot.get_chat(source_chat_id)
                group_title = group.title if group.title else group.username
            except Exception as e:
                logging.error(f"Ошибка получения информации о чате: {e}")
                group_title = "Неизвестный чат"

            # Формируем сообщение для администратора с информацией о регистрации
            registration_info = (
                f"Новый пользователь {('@' + message.from_user.first_name) if message.from_user.first_name and message.from_user.first_name != 'None' else message.from_user.first_name} (id: {user_id}) "
                f"подал запрос на регистрацию в чате {('@' + group_title) if group_title and group_title != 'None' else group_title} (id: {source_chat_id}).\n"
                f"Имя: {name}\n"
                f"Фамилия: {surname}\n"
                f"Квартира: {apartment}\n"
                f"Телефон: {phone}"
            )

            keyboard = InlineKeyboardMarkup(row_width=1)
            allow_button = InlineKeyboardButton("Дать доступ", callback_data=f"allow:{user_id}")
            deny_button = InlineKeyboardButton("Отклонить доступ", callback_data=f"deny:{user_id}")
            request_photo_button = InlineKeyboardButton("Запросить новое фото", callback_data=f"request_photo:{user_id}")
            keyboard.add(allow_button, deny_button, request_photo_button)

            # Отправляем информацию админу и подтверждаем получение фото пользователю
            bot.send_message(ADMIN_ID, registration_info)
            bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, reply_markup=keyboard)
            bot.send_message(user_id, "Фото получено. Ожидайте подтверждения.")

        user_state[user_id] = "photo_sent"

# Callback-обработчик для разрешения доступа (администратор подтверждает)
@bot.callback_query_handler(func=lambda call: call.data.startswith("allow:"))
def allow_access(call):
    user_id = int(call.data.split(":")[1])
    source_chat_id = get_source_chat_id(user_id)
    if source_chat_id is None:
        bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
        return
    logging.info(f"Перед обработкой кнопки 'Дать доступ' текущий source_chat_id: {source_chat_id}, пользователь: {user_id}")
    member = None
    try:
        member = bot.get_chat_member(source_chat_id, user_id)
        if member.status not in ['left', 'kicked']:
            logging.info(f"Пользователь {user_id} найден в чате {source_chat_id}")
    except Exception as e:
        logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
    try:
        # Снимаем ограничения и разрешаем отправку сообщений
        bot.restrict_chat_member(source_chat_id, user_id, can_send_messages=True)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Ошибка снятия ограничений для {user_id} в чате {source_chat_id}: {e}")
    if user_id not in pending_users:
        pending_users[user_id] = {'status': 'awaiting_photo', 'join_time': datetime.now()}
    pending_users[user_id]['status'] = 'approved'
    logging.info("Доступ открыт")
    bot.send_message(user_id, f"Доступ разрешён и вы можете пользоваться чатом жильцов" +
                     (f" (@{bot.get_chat(source_chat_id).username})" if bot.get_chat(source_chat_id).username else "") + ".")
    bot.send_message(source_chat_id, f"Приветствуем пользователя {('@' + member.user.first_name) if member.user.first_name else member.user.first_name}" +
                     (f" (@{member.user.username})" if member.user.username else ". Он получил доступ к чату."))
    bot.answer_callback_query(call.id, "Доступ предоставлен.")
    bot.send_message(ADMIN_ID, f"Доступ пользователю {('@' + member.user.first_name) if member.user.first_name else member.user.first_name} предоставлен.")

# Callback-обработчик для отклонения доступа (администратор отклоняет регистрацию)
@bot.callback_query_handler(func=lambda call: call.data.startswith("deny:"))
def deny_access(call):
    user_id = int(call.data.split(":")[1])
    source_chat_id = get_source_chat_id(user_id)
    if source_chat_id is None:
        bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
        return
    now = datetime.now().isoformat()
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET date_del = ? WHERE tg_id = ?", (now, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка обновления записи для {user_id} при отклонении: {e}")
    member = None
    try:
        member = bot.get_chat_member(source_chat_id, user_id)
    except Exception as e:
        logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
    try:
        bot.kick_chat_member(source_chat_id, user_id)
        bot.unban_chat_member(source_chat_id, user_id)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Ошибка удаления {user_id} из чата {source_chat_id}: {e}")
    bot.send_message(user_id, "Ваш запрос отклонён. Фото не соответствует требованиям.")
    if member is not None:
        group_msg = f"Пользователю {member.user.first_name}" + (f" ({member.user.username})" if member.user.username else " доступ не предоставлен, и он удалён.")
    else:
        group_msg = "Пользователь не найден, уведомление не отправлено."
    bot.send_message(source_chat_id, group_msg)
    bot.answer_callback_query(call.id, "Доступ отклонён!")
    admin_msg = f"Доступ пользователю {member.user.first_name if member is not None else user_id} отклонён и он удалён из чата ({source_chat_id})."
    bot.send_message(ADMIN_ID, admin_msg)

# Callback-обработчик для запроса нового фото (администратор запрашивает новое фото)
@bot.callback_query_handler(func=lambda call: call.data.startswith("request_photo:"))
def request_photo(call):
    user_id = int(call.data.split(":")[1])
    source_chat_id = get_source_chat_id(user_id)
    if source_chat_id is None:
        bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
        return
    logging.info(f"Запрос нового фото, source_chat_id: {source_chat_id}, пользователь: {user_id}")
    admin_state[ADMIN_ID] = {"user_id": user_id, "awaiting_reason": True}
    request_reason = f"Укажите причину запроса нового фото для пользователя {user_id}."
    bot.send_message(ADMIN_ID, request_reason)
    bot.answer_callback_query(call.id, "Введите причину запроса нового фото.")

# Обработчик сообщений от администратора для ввода причины запроса нового фото
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and not (message.text and message.text.startswith("/")))
def save_reason(message):
    global admin_state
    # Обрабатываем сообщение только если администратор находится в режиме ввода причины
    if ADMIN_ID not in admin_state or not admin_state[ADMIN_ID].get("awaiting_reason"):
        return
    user_id = admin_state[ADMIN_ID].get("user_id")
    if user_id is None:
        bot.send_message(ADMIN_ID, "Не найден user_id для ADMIN_ID.")
        return
    if user_id not in pending_users:
        pending_users[user_id] = {}
    pending_users[user_id]['reason'] = message.text
    bot.send_message(ADMIN_ID, "Причина сохранена.")
    reason = pending_users[user_id].get('reason', "причина не указана")
    user_msg = (f"Администратор запросил новое фото по причине: {reason}\n"
                f"Пожалуйста, отправьте новое фото для подтверждения доступа.")
    bot.send_message(user_id, user_msg)
    user_state[user_id] = "awaiting_new_photo"
    src_chat = get_source_chat_id(user_id)
    if src_chat is not None:
        try:
            member = bot.get_chat_member(src_chat, user_id)
            user_first_name = member.user.first_name if member.user.first_name else str(user_id)
        except Exception as e:
            logging.error(f"Ошибка получения информации для {user_id}: {e}")
            user_first_name = str(user_id)
        group_msg = (f"@{user_first_name}, администратор запросил новое фото. Проверьте личные сообщения.")
        bot.send_message(src_chat, group_msg)
    else:
        logging.error("src_chat не определён, уведомление не отправлено.")
    # Сбрасываем состояние администратора
    admin_state.pop(ADMIN_ID, None)

# Обработчик события выхода участника из чата
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
            logging.error(f"Ошибка закрытия БД для {user_id}: {e}")
    if user_id in pending_users:
        del pending_users[user_id]

# Callback-обработчик для идентификации (пользователь подтверждает проживание)
@bot.callback_query_handler(func=lambda call: call.data == 'identification')
def identification_handler(call):
    if call.message.chat is None:
        logging.error("call.message.chat is None, невозможно обработать идентификацию.")
        return
    user_id = call.from_user.id
    source_chat_id = get_source_chat_id(user_id)
    if source_chat_id is None:
        bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
        return
    logging.info(f"Идентификация для чата {source_chat_id} (ID: {call.message.chat.id})")
    keyboard = InlineKeyboardMarkup(row_width=1)
    # Кнопки для подтверждения проживания
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)
    bot.send_message(call.message.chat.id, "Пожалуйста подтвердите ваше проживание:", reply_markup=keyboard)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM groups")
    group_ids = cursor.fetchall()
    logging.info(f"Group IDs: {group_ids}")
    conn.close()

# Callback-обработчик для пользователей, которые подтверждают, что не являются жильцами
@bot.callback_query_handler(func=lambda call: call.data == "not_residing")
def not_residing_handler(call):
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Чат предназначен только для жильцов.")
    source_id = get_source_chat_id(user_id)
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
            logging.error(f"Ошибка удаления {user_id} из чата {source_id}: {e}")
    bot.answer_callback_query(call.id)

# Callback-обработчик для выбора опции "Да" при возвращении в группу
@bot.callback_query_handler(func=lambda call: call.data == "return_yes")
def return_yes_handler(call):
    user_id = call.from_user.id
    now = datetime.now().isoformat()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET date_del = NULL, date_add = ? WHERE tg_id = ?", (now, user_id))
    conn.commit()
    conn.close()
    bot.send_message(call.message.chat.id, "Отлично! Пожалуйста отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры.")
    user_state[user_id] = "awaiting_photo"
    bot.answer_callback_query(call.id)

# Callback-обработчик для выбора опции "Нет" при возвращении в группу
@bot.callback_query_handler(func=lambda call: call.data == "return_no")
def return_no_handler(call):
    bot.send_message(call.message.chat.id, "Ну, заходи если чё...")
    bot.answer_callback_query(call.id)

# Callback-обработчик для подтверждения проживания
@bot.callback_query_handler(func=lambda call: call.data == "confirm_residence")
def confirm_residence_handler(call):
    user_id = call.from_user.id
    source_chat = get_source_chat_id(user_id)
    house_id = None
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if source_chat:
         cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (source_chat,))
         house_row = cursor.fetchone()
         if house_row:
              house_id = house_row[0]
    cursor.execute("SELECT id, name, date_del FROM users WHERE tg_id = ? AND house = ?", (user_id, house_id))
    user_record = cursor.fetchone()
    if user_record:
        if not user_record[2] or user_record[2].strip() == "":
            bot.send_message(call.message.chat.id, f"{user_record[1]}, мы тебя узнали и ты уже зарегистрирован.")
            conn.close()
            bot.answer_callback_query(call.id)
            return
        else:
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id, f"Привет {user_record[1]}! Хотите вернуться в группу?", reply_markup=keyboard)
            conn.close()
            bot.answer_callback_query(call.id)
            return
    else:
         conn.close()
         bot.send_message(call.message.chat.id, "Ответьте на несколько вопросов, пожалуйста. Данные на серверах хранятся в зашифрованном виде.")
         ask_name(call.message.chat.id, user_id)
         bot.answer_callback_query(call.id)

# Функции для проведения опроса (анкеты)

def ask_name(chat_id, user_id):
    # Запрашиваем у пользователя его имя
    bot.send_message(chat_id, "Ваше имя:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_name(message, user_id))

def process_name(message, user_id):
    name = message.text.strip()
    if len(name) > 50:
        bot.send_message(message.chat.id, "Имя не должно превышать 50 символов. Введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    if any(bad in name.lower() for bad in banned_words):
        bot.send_message(message.chat.id, "Имя содержит недопустимые слова. Введите корректное имя.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_name(m, user_id))
        return
    now = datetime.now().isoformat()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Определяем исходный чат, из которого пользователь пришёл
    source_id = pending_users.get(user_id, {}).get('source_chat_id')
    house_id = None
    if source_id:
        cursor.execute("SELECT id FROM houses WHERE chat_id = ?", (source_id,))
        house = cursor.fetchone()
        if house is None:
            # Если дом не найден, создаем его
            cursor.execute("INSERT INTO houses (chat_id, date_add) VALUES (?, ?)", (source_id, now))
            house_id = cursor.lastrowid
        else:
            house_id = house[0]
    # Проверяем, существует ли запись пользователя для данного дома
    cursor.execute("SELECT id FROM users WHERE tg_id = ? AND house = ?", (user_id, house_id))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO users (tg_id, name, house, date_add) VALUES (?, ?, ?, ?)", (user_id, name, house_id, now))
    else:
        cursor.execute("UPDATE users SET name = ?, date_add = ? WHERE id = ?", (name, now, result[0]))
    conn.commit()
    conn.close()
    ask_surname(message.chat.id, user_id)

def ask_surname(chat_id, user_id):
    bot.send_message(chat_id, "Фамилия:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_surname(message, user_id))

def process_surname(message, user_id):
    surname = message.text.strip()
    if len(surname) > 50:
        bot.send_message(message.chat.id, "Фамилия не должна превышать 50 символов. Введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return
    banned_words = ['бляд', 'хуй', 'пизд', 'сука']
    if any(bad in surname.lower() for bad in banned_words):
        bot.send_message(message.chat.id, "Фамилия содержит недопустимые слова. Введите корректную фамилию.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_surname(m, user_id))
        return
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET surname = ? WHERE tg_id = ?", (surname, user_id))
    conn.commit()
    conn.close()
    ask_apartment(message.chat.id, user_id)

def ask_apartment(chat_id, user_id):
    bot.send_message(chat_id, "№ квартиры:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_apartment(message, user_id))

def process_apartment(message, user_id):
    apartment_str = message.text.strip()
    try:
        apartment = int(apartment_str)
        if apartment < 1 or apartment > 10000:
            raise ValueError("Номер квартиры должен быть от 1 до 10000")
    except ValueError as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}. Введите номер квартиры от 1 до 10000.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_apartment(m, user_id))
        return
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET apartment = ? WHERE tg_id = ?", (str(apartment), user_id))
    conn.commit()
    conn.close()
    ask_phone(message.chat.id, user_id)

def ask_phone(chat_id, user_id):
    bot.send_message(chat_id, "Телефон в формате +79002003030:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_phone(message, user_id))

def process_phone(message, user_id):
    phone = message.text.strip()
    try:
        phone_number = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(phone_number):
            raise ValueError("Номер не валидный")
        formatted_phone = format_number(phone_number, PhoneNumberFormat.E164)
    except Exception as e:
        bot.send_message(message.chat.id, f"Неверный формат телефона: {e}. Введите номер в формате +79002003030.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_phone(m, user_id))
        return
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (formatted_phone, user_id))
    conn.commit()
    conn.close()
    ask_car_count(message.chat.id, user_id)

def ask_car_count(chat_id, user_id):
    bot.send_message(chat_id, "Укажите, сколько у вас автомобилей (0 если нет):")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_count(message, user_id))

def process_car_count(message, user_id):
    try:
        count = int(message.text.strip())
        if count < 0 or count > 10:
            raise ValueError("Количество авто должно быть от 0 до 10")
    except ValueError as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}. Введите число от 0 до 10.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_count(m, user_id))
        return
    if count == 0:
        bot.send_message(message.chat.id, "Понятно, вы не автомобилист!")
        finalize_questionnaire(message.chat.id, user_id)
    else:
        user_state[user_id] = {"car_count": count, "current_car": 1}
        ask_car_number(message.chat.id, user_id)

def ask_car_number(chat_id, user_id):
    current = user_state[user_id]["current_car"]
    bot.send_message(chat_id, f"Номер авто {current} (например, н001нн797):")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_number(message, user_id))

def process_car_number(message, user_id):
    autonum = message.text.strip()
    if len(autonum) < 3 or len(autonum) > 15:
        bot.send_message(message.chat.id, "Номер авто должен содержать от 3 до 15 символов. Введите корректный номер.")
        bot.register_next_step_handler_by_chat_id(message.chat.id, lambda m: process_car_number(m, user_id))
        return
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

def finalize_questionnaire(chat_id, user_id):
    # Финальный шаг опроса – просим отправить фото дворовой территории
    bot.send_message(chat_id, "Анкета заполнена. Теперь отправьте актуальное фото дворовой территории из окна вашей квартиры.")
    user_state[user_id] = "awaiting_photo"

# Обработчик команды /db для администратора – выводит содержимое таблиц
@bot.message_handler(commands=['db'])
def db_handler(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа")
        return
    conn = sqlite3.connect('database.db')
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
    conn.close()
    max_length = 4096
    for i in range(0, len(output), max_length):
        bot.send_message(message.chat.id, output[i:i+max_length])

# Обработчик команды /check для администратора – проверяет регистрацию пользователей в указанном чате
@bot.message_handler(commands=['check'])
def check_handler(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    parts = message.text.split()
    if len(parts) >= 2:
        group_id_check = parts[1]
    else:
        bot.send_message(message.chat.id, "Укажите ID группы, например: /check -123456789")
        return
    not_registered = []
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT tg_id FROM chat_members WHERE chat_id = ?", (group_id_check,))
        stored_members = cursor.fetchall()
        conn.close()

        active_members = []
        for (tg_id,) in stored_members:
            try:
                member = bot.get_chat_member(group_id_check, tg_id)
                if member.status not in ['left', 'kicked']:
                    active_members.append(tg_id)
            except Exception as e:
                logging.error(f"Ошибка получения информации для пользователя {tg_id} в чате {group_id_check}: {e}")

        for tg_id in active_members:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT users.id FROM users 
                JOIN houses ON users.house = houses.id 
                WHERE users.tg_id = ? AND houses.chat_id = ?
            """, (tg_id, group_id_check))
            user_in_db = cursor.fetchone()
            conn.close()
            if not user_in_db:
                not_registered.append(tg_id)
                try:
                    bot.kick_chat_member(group_id_check, tg_id)
                    bot.unban_chat_member(group_id_check, tg_id)
                    bot.send_message(tg_id, "Вы не зарегистрированы. Заполните данные для доступа к чату.")
                except Exception as e:
                    logging.error(f"Ошибка блокировки {tg_id} в чате {group_id_check}: {e}")
        bot.send_message(message.chat.id,
                         f"Проверка завершена. Заблокировано {len(not_registered)} пользователей: {not_registered}")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")

# Обработчик команды /checkall для администратора – проверяет регистрацию во всех группах
@bot.message_handler(commands=['checkall'])
def checkall_handler(message):
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM chat_members")
        groups = cursor.fetchall()
        conn.close()
        total_blocked = 0
        details = ""
        for (grp_id,) in groups:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("SELECT tg_id FROM chat_members WHERE chat_id = ?", (grp_id,))
            members = cursor.fetchall()
            conn.close()
            not_registered = []
            for (tg_id,) in members:
                conn = sqlite3.connect('database.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
                user_in_db = cursor.fetchone()
                conn.close()
                if not user_in_db:
                    not_registered.append(tg_id)
                    try:
                        bot.kick_chat_member(grp_id, tg_id)
                        bot.unban_chat_member(grp_id, tg_id)
                        bot.send_message(tg_id, "Вы не зарегистрированы. Заполните данные для доступа к чату.")
                    except Exception as e:
                        logging.error(f"Ошибка блокировки {tg_id} в чате {grp_id}: {e}")
            total_blocked += len(not_registered)
            details += f"Чат {grp_id}: заблокировано {len(not_registered)} пользователей\n"
        bot.send_message(message.chat.id, f"Проверка завершена. Всего заблокировано {total_blocked} пользователей.\n{details}")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")

# -------------------- Обработчики подтверждения регистрации --------------------
@bot.callback_query_handler(func=lambda call: call.data == "confirm_registration_yes")
def confirm_registration_yes_handler(call):
    user_id = call.from_user.id
    # Запускаем полную регистрацию, начиная с запроса имени
    ask_name(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id, "Начинаем регистрацию")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_registration_no")
def confirm_registration_no_handler(call):
    user_id = call.from_user.id
    # Сообщаем пользователю об отказе и удаляем его из чата
    bot.send_message(call.message.chat.id, "Чат предназначен только для жителей дома. Сейчас мы вас из него удалим.")
    # Получаем исходный чат (групповый чат, откуда пользователь пришёл)
    source = get_source_chat_id(user_id)
    if source:
         try:
              bot.kick_chat_member(source, user_id)
              bot.unban_chat_member(source, user_id)
              bot.send_message(source, f"Пользователь {call.from_user.first_name} отказался от регистрации и удалён из чата.")
         except Exception as e:
              logging.error(f"Ошибка удаления пользователя {user_id} из чата {source}: {e}")
    bot.answer_callback_query(call.id, "Вы удалены из чата")

# -------------------- Запуск бота --------------------
bot.polling()