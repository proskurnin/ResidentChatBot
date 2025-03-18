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


conn = sqlite3.connect('database.db')
cursor = conn.cursor()
cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY
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
    global group_id
    group_id = message.chat.id  # Сохраняем ID текущей группы
    user_first_name = message.from_user.first_name or "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    identification_button = InlineKeyboardButton("Идентификация", callback_data="identification")
    keyboard.add(identification_button)
    bot.reply_to(message, f"Привет, {user_first_name}! Я бот чата жильцов. Закрытый чат жителей. Для участия нужно пройти идентификацию, так как в группу допускаются только жители.\n* обращайте внимание на правила в прикрепленном сообщении.\nИдентифицироваться можно по ссылке: Идентификация", reply_markup=keyboard)

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
                        can_send_messages=False,
                        until_date=int(datetime.now().timestamp()) + 7 * 24 * 3600
                    )
                except telebot.apihelper.ApiTelegramException as e:
                    logging.error(f"Ошибка ограничения для пользователя {new_member.id}: {e}")

            # Направляем нового участника в группу
            bot.send_message(
                group_id,
                f"Добро пожаловать, {new_member.first_name}! Чтобы получить доступ к чату, пожалуйста, отправьте фото из окна вашей квартиры администратору. Отправьте сообщение боту, чтобы подтвердить вашу личность по ссылке: https://t.me/{BOT_NAME}?start"
            )

@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    if message.from_user.id == bot.get_me().id:
        # Это фото отправлено администратору
        bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
    else:
        # Создаем клавиатуру с кнопками
        keyboard = InlineKeyboardMarkup(row_width=1)
        allow_button = InlineKeyboardButton("Дать доступ", callback_data=f"allow:{message.from_user.id}")
        deny_button = InlineKeyboardButton("Отклонить доступ", callback_data=f"deny:{message.from_user.id}")
        request_photo_button = InlineKeyboardButton("Запросить новое фото", callback_data=f"request_photo:{message.from_user.id}")
        keyboard.add(allow_button, deny_button, request_photo_button)

        # Отправляем фото админу
        bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, reply_markup=keyboard)
        bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")

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
    bot.send_message(call.message.chat.id, "Наш чат и все ресурсы предназначены для жителей. Очень просим Вас не беспокоить жителей в общей группе. Мы бы не хотели отвлекаться от решения наших вопросов.")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_residence")
def confirm_residence_handler(call):
    # Выводим сообщение с инструкцией
    bot.send_message(
        call.message.chat.id,
        "Пожалуйста, отправьте сейчас АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры. "
        "Фотография будет сверяться с фактической обстановкой модераторами. Указанная процедура требуется так, "
        "как в Чат допускаются только жильцы комплекса. Также, доступно подтверждение проживания по каким-либо документам. "
        "Если Вы хотите воспользоваться этим способом, пожалуйста, сообщите это администратору @proskurninra личным сообщением."
    )

bot.polling()