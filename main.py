import telebot
import logging
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup


import os
from dotenv import load_dotenv


# Загружаем переменные из .env
load_dotenv()

# Используем переменные
API_TOKEN = os.getenv("API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")
BOT_NAME = os.getenv("BOT_NAME")



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import sqlite3
admin_to_user_map = {}
user_state = {}  # Отслеживает состояние диалога в личном чате (ключ: tg_id)

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
        house_address TEXT
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
        FOREIGN KEY(house) REFERENCES houses(id)
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user INTEGER,
        autonum TEXT,
        FOREIGN KEY(user) REFERENCES users(id)
    )
''')
conn.commit()
conn.close()



if not API_TOKEN or not ADMIN_ID:
    raise ValueError("API_TOKEN и ADMIN_ID должны быть указаны в .env")


bot = telebot.TeleBot(API_TOKEN)
pending_users = {}  # Словарь для отслеживания новых участников
group_id = None  # Переменная для хранения ID текущей группы
source_chat_id = None  # Инициализация переменной



@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.chat.type != 'private':
        return  # /start обрабатывается только в личном чате
    user_first_name = message.from_user.first_name or "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    intro_button = InlineKeyboardButton("Познакомиться", callback_data="start_introduction")
    keyboard.add(intro_button)
    bot.send_message(message.chat.id, f"Привет, {user_first_name}! Я бот чата жильцов. Закрытый чат жителей. Для участия нужно познакомиться и пройти идентификацию. Это займёт 2 минуты.", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "start_introduction")
def start_introduction_handler(call):
    user_id = call.from_user.id
    user_state[user_id] = "awaiting_confirm"
    keyboard = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)
    bot.send_message(call.message.chat.id, "Пожалуйста, подтвердите ваше проживание:", reply_markup=keyboard)
    bot.answer_callback_query(call.id)

@bot.message_handler(content_types=['new_chat_members'])
def new_member_handler(message):
    global group_id
    group_id = message.chat.id  # Обновляем ID группы
    for new_member in message.new_chat_members:
        if new_member.id not in pending_users or pending_users[new_member.id]['status'] in ['approved', 'left']:
            # Заново запрашиваем фото у пользователей, которые вернулись
            pending_users[new_member.id] = {
                'status': 'awaiting_photo',
                'join_time': datetime.now(),
                'source_chat_id': group_id  # Сохраняем chat_id источника
            }
            # Ограничиваем нового участника
            if new_member.id != bot.get_me().id:
                try:
                    bot.restrict_chat_member(
                        group_id,
                        new_member.id,
                        can_send_messages=False
                    )
                except telebot.apihelper.ApiTelegramException as e:
                    logging.error(f"Ошибка ограничения для пользователя {new_member.id}: {e}")

            # Направляем нового участника в группу
            bot.send_message(
                group_id,
                f"Добро пожаловать, {new_member.first_name}! Чтобы получить доступ к чату, пожалуйста, пройдите процедуру знакомства и подтверждения. Чтобы получить доступ пройдите по ссылке: https://t.me/{BOT_NAME}?start"
            )

@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    user_id = message.from_user.id
    if user_state.get(user_id) == "awaiting_photo":
        if user_id == bot.get_me().id:
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            allow_button = InlineKeyboardButton("Дать доступ", callback_data=f"allow:{user_id}")
            deny_button = InlineKeyboardButton("Отклонить доступ", callback_data=f"deny:{user_id}")
            request_photo_button = InlineKeyboardButton("Запросить новое фото", callback_data=f"request_photo:{user_id}")
            keyboard.add(allow_button, deny_button, request_photo_button)
            bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, reply_markup=keyboard)
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        user_state[user_id] = "photo_sent"
    else:
        bot.send_message(message.chat.id, "Напоминаю, что я жду от вас фото для идентификации.")

# ПРЕДОСТАВЛЯЕМ ДОСТУП - Кнопка "Дать доступ"
@bot.callback_query_handler(func=lambda call: call.data.startswith("allow:"))
def allow_access(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(f"Перед обработкой кнопки 'Дать доступ' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")

    if source_chat_id:
        # Снимаем ограничения
        member = None
        try:
            member = bot.get_chat_member(source_chat_id, user_id)
            if member.status not in ['left', 'kicked']:
                logging.info(
                    f"Текущий пользователь {user_id} в исходном чате {source_chat_id} найден!")  # Успех поиска пользователя в исходном чате
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
        bot.send_message(user_id, f"Доступ разрешён и вы можете воспользоваться всеми возможностями группы жильцов" + (f" (@{bot.get_chat(source_chat_id).username})" if bot.get_chat(source_chat_id).username else "") + ".")
        bot.send_message(source_chat_id, f"Приветствуем пользователя {member.user.first_name}" + (f" ({member.user.username})" if member.user.username else ". Он получает доступ ко всем возможностям группы. Поздравляем!"))
        logging.info(f"call.id: {call.id}")
        bot.answer_callback_query(call.id, "Доступ предоставлен.")
        bot.send_message(chat_id=ADMIN_ID, text=f"Доступ пользователю {member.user.first_name}" + (f" (@{member.user.username})" if member.user.username else "") + " предоставлен.")

    else:
        bot.send_message(user_id, f"Группа не определена ({source_chat_id})!\nОшибка снятия ограничений для пользователя {user_id}!")

# ОТКЛОНЯЕМ ДОСТУП - Кнопка "Отклонить доступ"
@bot.callback_query_handler(func=lambda call: call.data.startswith("deny:"))
def deny_access(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(
        f"Перед обработкой кнопки 'Отклонить доступ' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")

    # Удаляем пользователя
    member = None
    try:
        member = bot.get_chat_member(source_chat_id, user_id)
        if member.status not in ['left', 'kicked']:
            logging.info(
                f"Текущий пользователь {user_id} в исходном чате {source_chat_id} найден!")  # Успех поиска пользователя в исходном чате
    except Exception as e:
        logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
    if source_chat_id:
        try: # активность вся тут
            bot.kick_chat_member(source_chat_id, user_id)
            bot.unban_chat_member(source_chat_id, user_id) # Удаляем пользователя из Чёрного списка. Потому что мы ему должны дать возможность вернуться
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка отклонения запроса и удаления пользователя {user_id} из чата {source_chat_id}: {e}")
    else:
        logging.error(f"Пользователь {user_id} не найден ни в одном известном чате.")

    logging.info("Доступ ОТКЛОНЁН и пользователь УДАЛЁН")
    bot.send_message(user_id, f"Ваш запрос отклонён, потому что вы прислали не релевантное фото. Напоминаю, что следовало прислать фото вида из окна вашей квартиры, которое вы сделали сегодня.")
    bot.send_message(source_chat_id, f"Пользователю {member.user.first_name}" + (f" ({member.user.username})" if member.user.username else " доступ не предоставлен и он удалён за предоставление не релевантной фотографии."))
    logging.info(f"call.id: {call.id}")
    bot.answer_callback_query(call.id, "Доступ отклонён!")
    bot.send_message(chat_id=ADMIN_ID, text=f"Доступ пользователю {member.user.first_name}" + (f" (@{member.user.username})" if member.user.username else "") + f" ОТКЛОНЁН и он УДАЛЁН из группы ({source_chat_id}).")

# ЗАПРОС ДРУГОГО ФОТО - Кнопка "Запросить новое фото"
@bot.callback_query_handler(func=lambda call: call.data.startswith("request_photo:"))
@bot.callback_query_handler(func=lambda call: call.data.startswith("request_photo:"))
def request_photo(call):
    global group_id, source_chat_id
    user_id = int(call.data.split(":")[1])
    source_chat_id = pending_users.get(user_id, {}).get('source_chat_id', group_id)
    logging.info(
        f"Перед обработкой кнопки 'Запросить новое фото' текущий source_chat_id: {source_chat_id}, текущий пользователь user_id: {user_id} и текущий group_id: {group_id}")

    admin_to_user_map[ADMIN_ID] = user_id
    # Запрашиваем причину
    request_reason = f"Пожалуйста, укажите причину для запроса нового фото от @{user_id}."
    bot.send_message(ADMIN_ID, request_reason)

# Обработчик причины почему нужна новая фотография
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

# Новый обработчик на случай, если пользователь покидает группу
@bot.message_handler(content_types=['left_chat_member'])
def left_member_handler(message):
    left_user = message.left_chat_member
    if left_user.id in pending_users:
        pending_users[left_user.id]['status'] = 'left'

@bot.callback_query_handler(func=lambda call: call.data == 'identification')
def identification_handler(call):
    global group_id, source_chat_id
    if call.message.chat is None:
        logging.error("call.message.chat is None, cannot process identification.")
        return
    user_id = call.from_user.id
    if user_id in pending_users:
        source_chat_id = pending_users[user_id]['source_chat_id']  # Получаем сохранённый chat_id
    logging.info(f"Обработчик вызван для группы {source_chat_id} (ID: {call.message.chat.id})")
    keyboard = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)

    bot.send_message(call.message.chat.id, "Пожалуйста, подтвердите ваше проживание:", reply_markup=keyboard)
    # Подключаемся к базе данных
    import sqlite3
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM groups")
    group_ids = cursor.fetchall()
    logging.info(f"Group IDs: {group_ids}")
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data == "not_residing")
def not_residing_handler(call):
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Чат предназначен только для жильцов.")
    source_id = pending_users.get(user_id, {}).get('source_chat_id')
    if source_id:
        try:
            bot.kick_chat_member(source_id, user_id)
            bot.unban_chat_member(source_id, user_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка удаления пользователя {user_id} из чата {source_id}: {e}")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "confirm_residence")
def confirm_residence_handler(call):
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Ответьте на несколько вопросов, пожалуйста. Данные на серверах хранятся в зашифрованном виде в соответствии с требованиями регулятора.")
    ask_name(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id)

import sqlite3

def ask_name(chat_id, user_id):
    bot.send_message(chat_id, "Ваше имя:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_name(message, user_id))

def process_name(message, user_id):
    name = message.text.strip()
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
                cursor.execute("INSERT INTO houses (chat_id) VALUES (?)", (source_id,))
                house_id = cursor.lastrowid
            else:
                house_id = house[0]
        cursor.execute("INSERT INTO users (tg_id, name, house) VALUES (?, ?, ?)", (user_id, name, house_id))
    else:
        cursor.execute("UPDATE users SET name = ? WHERE tg_id = ?", (name, user_id))
    conn.commit()
    conn.close()
    ask_surname(message.chat.id, user_id)

def ask_surname(chat_id, user_id):
    bot.send_message(chat_id, "Фамилия:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_surname(message, user_id))

def process_surname(message, user_id):
    surname = message.text.strip()
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
    apartment = message.text.strip()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET apartment = ? WHERE tg_id = ?", (apartment, user_id))
    conn.commit()
    conn.close()
    ask_phone(message.chat.id, user_id)

def ask_phone(chat_id, user_id):
    bot.send_message(chat_id, "Телефон в формате +79002003030:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_phone(message, user_id))

def process_phone(message, user_id):
    phone = message.text.strip()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, user_id))
    conn.commit()
    conn.close()
    ask_car_count(message.chat.id, user_id)

def ask_car_count(chat_id, user_id):
    bot.send_message(chat_id, "Для помощи автомобилистам укажите сколько у вас автомобилей. Если машин нет, то укажите 0:")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_count(message, user_id))

def process_car_count(message, user_id):
    try:
        count = int(message.text.strip())
    except ValueError:
        count = 0
    if count == 0:
        bot.send_message(message.chat.id, "Понял, вы не автомобилист!")
        finalize_questionnaire(message.chat.id, user_id)
    else:
        user_state[user_id] = {"car_count": count, "current_car": 1}
        ask_car_number(message.chat.id, user_id)

def ask_car_number(chat_id, user_id):
    current = user_state[user_id]["current_car"]
    bot.send_message(chat_id, f"Номер авто {current} в формате н001нн797 (буквы русские):")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: process_car_number(message, user_id))

def process_car_number(message, user_id):
    autonum = message.text.strip()
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_id = ?", (user_id,))
    user_record = cursor.fetchone()
    if user_record:
        cursor.execute("INSERT INTO cars (user, autonum) VALUES (?, ?)", (user_record[0], autonum))
    conn.commit()
    conn.close()
    user_state[user_id]["current_car"] += 1
    if user_state[user_id]["current_car"] <= user_state[user_id]["car_count"]:
        ask_car_number(message.chat.id, user_id)
    else:
        finalize_questionnaire(message.chat.id, user_id)

def finalize_questionnaire(chat_id, user_id):
    bot.send_message(chat_id, "Спасибо, анкета заполнена. Теперь, пожалуйста, отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры. Фотография будет сверяться с фактической обстановкой модераторами. Если Вы хотите воспользоваться подтверждением по документам, сообщите это администратору @proskurninra личным сообщением.")
    user_state[user_id] = "awaiting_photo"

@bot.message_handler(commands=['db'])
def db_handler(message):
    # Команда доступна только для администратора
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа")
        return
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    output = "Таблица houses\n"
    cursor.execute("SELECT * FROM houses")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    output += "\nТаблица users\n"
    cursor.execute("SELECT * FROM users")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    output += "\nТаблица cars\n"
    cursor.execute("SELECT * FROM cars")
    for row in cursor.fetchall():
        output += " | ".join(map(str, row)) + "\n"
    conn.close()
    bot.send_message(message.chat.id, output)

bot.polling()