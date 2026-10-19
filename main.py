"""ResidentChatBot main module
============================
Этот модуль реализует Telegram-бота для управления процессом регистрации и идентификации жильцов.
Бот обрабатывает команды, новые входы в чат, идентификацию посредством отправки фото, а также проводит опрос для регистрации.
Конфигурация централизована в config.py, а данные сохраняются в SQLite базе данных.
"""

# ====================================================================
# ResidentChatBot
# ====================================================================
# Данный модуль отвечает за взаимодействие с пользователями через Telegram.
# Основные функции:
#   - Регистрация новых пользователей и идентификация жильцов.
#   - Валидация и сохранение данных (имя, фамилия, номер квартиры, телефон, автомобили и т.д.).
#   - Управление доступом в групповой чат: бот может ограничивать возможности новых участников,
#     отправлять уведомления администратору и пользователям, а также подтверждать регистрацию.
#   - Хранение и обновление данных в SQLite базе данных.
#
# Используемые технологии:
#   - Telebot (pyTelegramBotAPI) для работы с Telegram API.
#   - SQLite для хранения данных.
#   - dotenv для загрузки настроек из файла .env.
#   - phonenumbers для проверки формата телефонных номеров.
#
# Весь функционал структурирован в виде отдельных функций и обработчиков, что позволяет легко масштабировать
# и модифицировать работу бота.
# ====================================================================

# -------------------------------
# Импорт необходимых библиотек
# -------------------------------
import telebot               # telebot: для взаимодействия с Telegram Bot API.
import logging               # logging: для логирования действий и ошибок.
from datetime import datetime, timedelta  # datetime: для работы с датами и временем.
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
# telebot.types: предоставляет классы для создания интерактивных клавиатур.
import time
from config import ADMIN_ID, API_TOKEN, BOT_NAME, DB_FILE, LOG_LEVEL_NAME, TELEGRAM_PROXY
from repositories.db import (
    count_active_users_by_house,
    activate_cars_by_tg,
    get_active_user_count_by_tg,
    ensure_house_exists,
    get_active_house_rows,
    get_active_user_tg_ids_by_house,
    get_active_user_rows_by_house,
    get_house_chat_rows_by_user_tg,
    get_house_id_by_chat_id,
    get_any_user_id_by_tg,
    get_user_basic_profile_by_tg,
    get_user_full_record_by_tg_and_house,
    get_user_record_by_tg_and_house,
    get_user_id_by_tg_and_house,
    get_user_id_by_tg_and_null_house,
    get_user_registration_profile_by_tg,
    initialize_schema,
    dump_tables_text,
    insert_application,
    record_admin_action,
    update_latest_application_status_by_tg_and_house,
    mark_cars_date_del_by_tg,
    mark_cars_date_del_by_user_id,
    mark_user_date_del_by_tg_and_house,
    search_active_user_rows_by_apartment,
    insert_user,
    update_user_name_by_id,
    update_user_phone_by_id,
    update_user_surname_by_id,
    update_user_date_add_date_del_by_tg_and_house,
    update_user_house_date_add_date_del_by_tg_null_house,
)
import registration
from requests.exceptions import RequestException

# -------------------------------
# Настройка логирования
# -------------------------------
# Логирование настроено на вывод времени, уровня и текста сообщения.
logging.basicConfig(level=getattr(logging, LOG_LEVEL_NAME, logging.INFO), format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# -------------------------------
# Глобальные словари для отслеживания состояний
# -------------------------------
admin_to_user_map = {}  # Предполагаемый маппинг между администратором и пользователями (пока не используется).
user_state = {}         # Словарь для хранения состояния диалога с каждым пользователем (ключ – tg_id).
admin_state = {}        # Состояние администратора, например, при запросе нового фото.

# -------------------------------
# Инициализация базы данных
# -------------------------------
initialize_schema(DB_FILE)

# -------------------------------
# Инициализация Telegram-бота
# -------------------------------
if TELEGRAM_PROXY:
    telebot.apihelper.proxy = {
        "http": TELEGRAM_PROXY,
        "https": TELEGRAM_PROXY,
    }
bot = telebot.TeleBot(API_TOKEN)
logging.info(
    "ResidentChatBot started: db=%s, proxy=%s, log_level=%s",
    DB_FILE,
    "enabled" if TELEGRAM_PROXY else "disabled",
    LOG_LEVEL_NAME,
)

# Словарь pending_users хранит данные о новых участниках:
#   - status: текущий статус регистрации (например, 'awaiting_photo').
#   - join_time: время присоединения к чату.
#   - source_chat_id: ID исходного чата, откуда пользователь был добавлен.
pending_users = {}
group_id = None         # Переменная для хранения ID текущей группы (используется в некоторых местах).
source_chat_id = None   # Переменная для хранения исходного chat_id (используется при регистрации).

registration.init_registration(bot, DB_FILE, pending_users, user_state)

# ====================================================================
# Функция get_source_chat_id
# ====================================================================
def get_source_chat_id(user_id):
    """
    Определяет исходный групповой чат (source_chat_id) для пользователя:
      - Если в словаре pending_users уже есть значение, возвращает его.
      - Иначе ищет в базе данных дома, где пользователь зарегистрирован.
          * Если найден ровно один дом, сохраняет и возвращает chat_id этого дома.
          * Если найдено несколько домов, отправляет админу инлайн-клавиатуру для выбора нужного чата.
          * Если домов нет, возвращает None.
    """
    if user_id in pending_users and pending_users[user_id].get('source_chat_id'):
        return pending_users[user_id]['source_chat_id']
    rows = get_house_chat_rows_by_user_tg(DB_FILE, user_id)
    if len(rows) == 1:
         pending_users[user_id] = pending_users.get(user_id, {})
         pending_users[user_id]['source_chat_id'] = rows[0][0]
         return rows[0][0]
    elif len(rows) > 1:
         # Если пользователь зарегистрирован сразу в нескольких домах, просим администратора выбрать нужный чат.
         keyboard = InlineKeyboardMarkup(row_width=1)
         for chat, house_name in rows:
              button_text = f"{house_name} ({chat})" if house_name else f"Чат {chat}"
              button = InlineKeyboardButton(button_text, callback_data=f"choose_source:{user_id}:{chat}")
              keyboard.add(button)
         bot.send_message(ADMIN_ID, f"Выберите чат пользователя с id {user_id}", reply_markup=keyboard)
         return None
    else:
         return None

# ====================================================================
# Callback-обработчик выбора исходного чата администратором
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("choose_source:"))
def choose_source_handler(call):
    """
    Обрабатывает выбор чата администратором:
      - Из callback_data извлекает user_id и выбранный chat_id.
      - Сохраняет выбранный chat_id в словаре pending_users.
      - Отправляет подтверждение админу.
    """
    parts = call.data.split(":")
    if len(parts) == 3:
         user_id = int(parts[1])
         chosen_chat_id = parts[2]
         if user_id not in pending_users:
              pending_users[user_id] = {}
         pending_users[user_id]['source_chat_id'] = chosen_chat_id
         bot.answer_callback_query(call.id, "Чат выбран.")
         bot.send_message(ADMIN_ID, f"Для пользователя {user_id} выбран чат {chosen_chat_id}.")

# ====================================================================
# Обработчик команды /start в личном чате
# ====================================================================
@bot.message_handler(commands=['start'])
def start_handler(message):
    """
    Обрабатывает команду /start:
      - Работает только в приватном (личном) чате.
      - Отправляет приветственное сообщение и три кнопки для выбора действия:
          1. "Регистрация в чате" — запускает процесс регистрации (callback_data: start_introduction).
          2. "Полезная информация" — заглушка, которая выводит сообщение "Функция пока не реализована".
          3. "Написать администратору" — заглушка, которая выводит сообщение "Функция пока не реализована".
    """
    if message.chat.type != 'private':
        return
    user_first_name = f"@{message.from_user.first_name}" if message.from_user.first_name else "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    reg_button = InlineKeyboardButton("Регистрация в чате", callback_data="start_introduction")
    info_button = InlineKeyboardButton("Полезная информация", callback_data="info_placeholder")
    admin_button = InlineKeyboardButton("Написать администратору", callback_data="admin_placeholder")
    keyboard.add(reg_button, info_button, admin_button)
    bot.send_message(message.chat.id,
        f"Привет, {user_first_name}! Я бот чата жильцов из закрытого домового чата. Выбирай задачу, с которой тебе нужно помочь:",
        reply_markup=keyboard)

# ====================================================================
# Callback-обработчик кнопок "Полезная информация" и "Написать администратору" (пока заглушки)
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "info_placeholder")
def info_placeholder_handler(call):
    bot.send_message(call.message.chat.id, "Функция пока не реализована")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_placeholder")
def admin_placeholder_handler(call):
    bot.send_message(call.message.chat.id, "Функция пока не реализована")
    bot.answer_callback_query(call.id)

# ====================================================================
# Обработчик команды /newuser в личном чате
# ====================================================================
@bot.message_handler(commands=['newuser'])
def start_handler(message):
    """
    Обрабатывает команду /newuser:
      - Работает только в приватном (личном) чате.
      - Отправляет приветственное сообщение и кнопку для начала знакомства/регистрации.
    """
    if message.chat.type != 'private':
        return
    user_first_name = f"@{message.from_user.first_name}" if message.from_user.first_name else "сосед"
    keyboard = InlineKeyboardMarkup(row_width=1)
    # Кнопка для начала процесса регистрации
    intro_button = InlineKeyboardButton("Познакомиться", callback_data="start_introduction")
    keyboard.add(intro_button)
    bot.send_message(message.chat.id,
        f"Привет, {user_first_name}! Я бот чата жильцов. Закрытый чат жителей. Для участия нужно познакомиться и пройти идентификацию. Это займёт 2 минуты.",
        reply_markup=keyboard)

# ====================================================================
# Callback-обработчик кнопок "Познакомиться" и "Регистрация в чате"
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "start_introduction")
def start_introduction_handler(call):
    """
    Обрабатывает нажатие кнопки "Познакомиться":
      - Определяет исходный чат (source_chat_id), откуда пользователь пришёл.
      - Сравнивает полученный chat_id с данными из базы и словаря pending_users.
      - Если пользователь уже зарегистрирован в данном доме, предлагает варианты (вернуться в группу или уведомление о регистрации).
      - Если пользователь новый или зарегистрирован для другого дома, запускается процесс полной регистрации (опрос).
    """
    logging.info(f"start_introduction_handler вызван для пользователя: {call.from_user.id} в чате: {call.message.chat.id}")
    user_id = call.from_user.id
    user_first_name = f"@{call.from_user.first_name}" if call.from_user.first_name else "сосед"
    # Определяем источник сообщения: если из приватного чата и в pending_users уже есть source_chat_id, то используем его.
    if call.message.chat.type == "private" and user_id in pending_users and pending_users[user_id].get('source_chat_id'):
         current_source_chat = pending_users[user_id]['source_chat_id']
         logging.info(f"Сообщение из приватного чата. Используем сохранённый source_chat: {current_source_chat}")
    else:
         current_source_chat = call.message.chat.id
         logging.info(f"Используем текущий chat.id в качестве source_chat: {current_source_chat}")

    # Обновляем или сохраняем source_chat в pending_users
    db_source = get_source_chat_id(user_id)
    if db_source is None or db_source != current_source_chat:
         source_chat = current_source_chat
         pending_users[user_id] = pending_users.get(user_id, {})
         pending_users[user_id]['source_chat_id'] = current_source_chat
         logging.info(f"Устанавливаем source_chat для пользователя {user_id}: {current_source_chat}")
    else:
         source_chat = db_source
         logging.info(f"Используем существующий source_chat для пользователя {user_id}: {db_source}")

    # Проверяем наличие записи о доме (чат) в таблице houses
    house_id = get_house_id_by_chat_id(DB_FILE, source_chat)
    if house_id:
        logging.info(f"Найден дом для чата {source_chat}: house_id = {house_id}")
    else:
        logging.info(f"Дом для чата {source_chat} не найден")

    # Проверяем, зарегистрирован ли пользователь для этого дома
    user_record = get_user_record_by_tg_and_house(DB_FILE, user_id, house_id)
    logging.info(f"Проверка регистрации пользователя {user_id} для дома {house_id}: user_record = {user_record}")

    if user_record:
        # Если пользователь уже зарегистрирован, проверяем статус подтверждения регистрации
        if user_record[2] and user_record[2].strip() != "":
            logging.info(f"Пользователь {user_id} уже зарегистрирован в доме {house_id}. Отправляем предложение вернуться в группу.")
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id,
                             f"А мы вас знаем {user_first_name}! Хотите вернуться в группу?",
                             reply_markup=keyboard)
        else:
            logging.info(f"Пользователь {user_id} зарегистрирован, но не подтверждён. Отправляем сообщение об этом.")
            bot.send_message(call.message.chat.id,
                             f"{('@' + user_record[1]) if user_record[1] and user_record[1] != 'None' else ''}, мы тебя узнали и ты уже зарегистрирован.")
        bot.answer_callback_query(call.id)
        return
    else:
        # Если пользователь не зарегистрирован для этого дома
        logging.info(f"Пользователь {user_id} не зарегистрирован для дома {house_id}. Запускаем процесс регистрации.")
        # Если пользователь уже существует в БД (зарегистрирован в другом доме), добавляем новую запись для текущего дома.
        existing = get_any_user_id_by_tg(DB_FILE, user_id)
        if existing:
            logging.info(f"Пользователь {user_id} уже есть в БД, но не зарегистрирован для текущего дома {house_id}.")
            # Извлекаем уже сохраненные данные для повторного использования.
            data = get_user_registration_profile_by_tg(DB_FILE, user_id)
            if data:
                name_existing, surname_existing, phone_existing = data
            else:
                name_existing = call.from_user.first_name
                surname_existing = ""
                phone_existing = ""
            now = datetime.now().isoformat()
            # Ищем существующую запись для данного пользователя в текущем доме.
            record = get_user_full_record_by_tg_and_house(DB_FILE, user_id, house_id)
            if record:
                # Если запись найдена, обновляем её, сбрасывая date_del.
                update_user_name_by_id(DB_FILE, record[0], name_existing)
                update_user_surname_by_id(DB_FILE, record[0], surname_existing)
                update_user_phone_by_id(DB_FILE, record[0], phone_existing)
            else:
                # Если записи нет, вставляем новую для текущего дома.
                insert_user(DB_FILE, user_id, name_existing, house_id)
                new_record = get_user_full_record_by_tg_and_house(DB_FILE, user_id, house_id)
                if new_record:
                    update_user_name_by_id(DB_FILE, new_record[0], name_existing)
                    update_user_surname_by_id(DB_FILE, new_record[0], surname_existing)
                    update_user_phone_by_id(DB_FILE, new_record[0], phone_existing)
            # Устанавливаем состояние для запроса номера квартиры в новом доме.
            user_state[user_id] = "awaiting_apartment_new_house"
            bot.send_message(user_id,
                             f"Привет {name_existing}! Ты регистрируешься из нового дома {source_chat}. Введи, пожалуйста, номер квартиры для этого дома.")
            bot.register_next_step_handler_by_chat_id(user_id, lambda m: registration.process_apartment(m, user_id))
            bot.answer_callback_query(call.id)
            return
        else:
            # Новый пользователь – запускается полный процесс регистрации (опрос).
            logging.info(f"Пользователь {user_id} новый. Запускаем полный процесс регистрации.")
            registration.ask_registration_confirmation(call.message.chat.id, user_id)
            bot.answer_callback_query(call.id)
            return

# ====================================================================
# Обработчик новых участников в групповом чате
# ====================================================================
@bot.message_handler(content_types=['new_chat_members'])
def new_member_handler(message):
    """
    Обрабатывает событие добавления новых участников в групповой чат:
      - Проверяет, существует ли запись о данном чате (доме) в таблице houses; если нет – создаёт её.
      - Для каждого нового участника сохраняет статус (ожидание фото), время вступления и исходный chat_id.
      - Ограничивает возможность отправки сообщений новыми участниками (исключая самого бота).
      - Отправляет приветственное сообщение с кнопкой для получения доступа, которая ведет к началу регистрации.
    """
    logging.info("new_member_handler вызван")
    chat_id = message.chat.id
    # Проверяем наличие записи о чате в таблице houses
    now = datetime.now().isoformat()
    ensure_house_exists(DB_FILE, chat_id, now)

    # Для каждого нового участника выполняем сохранение данных и отправку уведомления.
    for new_member in message.new_chat_members:
        pending_users[new_member.id] = {
            'status': 'awaiting_photo',
            'join_time': datetime.now(),
            'source_chat_id': chat_id  # Сохраняем ID исходного группового чата.
        }
        # Если новый участник не является ботом, ограничиваем возможность отправки сообщений.
        if new_member.id != bot.get_me().id:
            try:
                bot.restrict_chat_member(chat_id, new_member.id, can_send_messages=False)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f"Ошибка ограничения для пользователя {new_member.id}: {e}")
            keyboard = InlineKeyboardMarkup(row_width=1)
            access_button = InlineKeyboardButton("Получить доступ", url=f"https://t.me/{BOT_NAME}?start=newuser")
            keyboard.add(access_button)
            bot.send_message(chat_id,
                f"Добро пожаловать, @{new_member.first_name}! Чтобы получить доступ к чату, пройдите процедуру знакомства и подтверждения. Нажмите кнопку ниже.",
                reply_markup=keyboard)

# ====================================================================
# Обработчик фотографий для идентификации пользователя
# ====================================================================
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    """
    Обрабатывает отправку фото для идентификации:
      - Проверяет, находится ли пользователь в состоянии ожидания фото (первичное или новое фото).
      - Если пользователь – бот, отправляет стандартное сообщение.
      - В остальных случаях извлекает данные пользователя из базы и определяет исходный групповой чат.
      - Формирует и отправляет админу сообщение с данными регистрации и фото.
      - Обновляет состояние пользователя на "photo_sent".
    """
    user_id = message.from_user.id
    if user_state.get(user_id) in ["awaiting_photo", "awaiting_new_photo"]:
        if user_id == bot.get_me().id:
            bot.send_message(message.from_user.id, "Фото получено. Ожидайте подтверждения.")
        else:
            # Извлекаем данные пользователя из БД для формирования сообщения.
            user_info = get_user_basic_profile_by_tg(DB_FILE, user_id)
            if user_info:
                name, surname, apartment, phone = user_info
            else:
                name = message.from_user.first_name
                surname = ""
                apartment = "не указана"
                phone = "не указан"

            # Определяем исходный групповой чат для пользователя.
            source_chat_id = get_source_chat_id(user_id)
            if source_chat_id is None:
                bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
                return

            # Пытаемся получить информацию о чате (название или username) для включения в сообщение.
            try:
                group = bot.get_chat(source_chat_id)
                group_title = group.title if group.title else group.username
            except Exception as e:
                logging.error(f"Ошибка получения информации о чате: {e}")
                group_title = "Неизвестный чат"

            # Формируем текстовое сообщение с информацией о регистрации для администратора.
            registration_info = (
                f"Новый пользователь {('@' + message.from_user.first_name) if message.from_user.first_name and message.from_user.first_name != 'None' else message.from_user.first_name} (id: {user_id}) "
                f"подал запрос на регистрацию в чате {('@' + group_title) if group_title and group_title != 'None' else group_title} (id: {source_chat_id}).\n"
                f"Имя: {name}\n"
                f"Фамилия: {surname}\n"
                f"Квартира: {apartment}\n"
                f"Телефон: {phone}"
            )

            keyboard = InlineKeyboardMarkup(row_width=1)
            # Формируем кнопки для администратора: дать доступ, отклонить, запросить новое фото.
            allow_button = InlineKeyboardButton("Дать доступ", callback_data=f"allow:{user_id}")
            deny_button = InlineKeyboardButton("Отклонить доступ", callback_data=f"deny:{user_id}")
            request_photo_button = InlineKeyboardButton("Запросить новое фото", callback_data=f"request_photo:{user_id}")
            keyboard.add(allow_button, deny_button, request_photo_button)

            # Отправляем собранную информацию и фото админу.
            bot.send_message(ADMIN_ID, registration_info)
            bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, reply_markup=keyboard)
            try:
                user_record_id = get_user_id_by_tg_and_house(DB_FILE, user_id, house_id) if house_id is not None else get_user_id_by_tg_and_null_house(DB_FILE, user_id)
                now = datetime.now().isoformat()
                insert_application(
                    DB_FILE,
                    user_id,
                    user_record_id,
                    house_id,
                    source_chat_id,
                    name,
                    surname,
                    apartment,
                    phone,
                    message.photo[-1].file_id,
                    "pending_review",
                    now,
                    now,
                )
            except Exception as e:
                logging.error("Ошибка сохранения заявки для web dashboard: %s", e)
            # Уведомляем пользователя о получении фото.
            bot.send_message(user_id, "Фото получено. Ожидайте подтверждения.")

        # Обновляем состояние пользователя после отправки фото.
        user_state[user_id] = "photo_sent"

# ====================================================================
# Callback-обработчик: разрешение доступа администратором
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("allow:"))
def allow_access(call):
    """
    Обрабатывает нажатие кнопки "Дать доступ":
      - Извлекает user_id из callback_data.
      - Определяет исходный групповой чат, снимает ограничения для отправки сообщений.
      - Обновляет статус пользователя в pending_users и записывает дату регистрации.
      - Отправляет уведомления как пользователю, так и в групповой чат, и информирует администратора.
    """
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
        # Снимаем ограничения, позволяя пользователю отправлять сообщения.
        bot.restrict_chat_member(source_chat_id, user_id, can_send_messages=True)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Ошибка снятия ограничений для {user_id} в чате {source_chat_id}: {e}")
    if user_id not in pending_users:
        pending_users[user_id] = {'status': 'awaiting_photo', 'join_time': datetime.now()}
    pending_users[user_id]['status'] = 'approved'
    logging.info("Доступ открыт")

    now = datetime.now().isoformat()
    house_id = get_house_id_by_chat_id(DB_FILE, source_chat_id)
    if house_id:
        # Сначала пытаемся найти запись пользователя для данного дома (существующего пользователя)
        record = get_user_record_by_tg_and_house(DB_FILE, user_id, house_id)
        if record:
            # Существующий пользователь: обновляем дату регистрации и сбрасываем date_del для данного дома.
            update_user_date_add_date_del_by_tg_and_house(DB_FILE, user_id, house_id, now)
        else:
            # Новый пользователь: обновляем запись, где house равен NULL, устанавливая house, дату регистрации и сбрасывая date_del.
            update_user_house_date_add_date_del_by_tg_null_house(DB_FILE, user_id, house_id, now)

        # После обновления записи пользователя сбрасываем date_del и устанавливаем date_add для всех записей автомобилей этого пользователя.
        activate_cars_by_tg(DB_FILE, user_id, now)
        try:
            application_id = update_latest_application_status_by_tg_and_house(
                DB_FILE,
                user_id,
                house_id,
                "approved",
                now,
                decided_at=now,
                decided_by=ADMIN_ID,
            )
            if application_id:
                record_admin_action(DB_FILE, application_id, ADMIN_ID, "allow", None, now)
        except Exception as e:
            logging.error("Ошибка обновления статуса заявки при allow: %s", e)

    bot.send_message(user_id, f"Доступ разрешён и вы можете пользоваться чатом жильцов" +
                     (f" (@{bot.get_chat(source_chat_id).username})" if bot.get_chat(source_chat_id).username else "") + ".")
    bot.send_message(source_chat_id, f"Приветствуем пользователя {('@' + member.user.first_name) if member.user.first_name else member.user.first_name}" +
                     (f" (@{member.user.username})" if member.user.username else ". Он получил доступ к чату."))
    bot.answer_callback_query(call.id, "Доступ предоставлен.")
    bot.send_message(ADMIN_ID, f"Доступ пользователю {('@' + member.user.first_name) if member.user.first_name else member.user.first_name} предоставлен.")

# ====================================================================
# Callback-обработчик: отклонение доступа администратором
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("deny:"))
def deny_access(call):
    """
    Обрабатывает нажатие кнопки "Отклонить доступ":
      - Обновляет запись пользователя, устанавливая дату удаления (date_del).
      - Пытается удалить пользователя из группового чата (kick + unban).
      - Уведомляет пользователя и групповой чат об отклонении, а также информирует администратора.
    """
    user_id = int(call.data.split(":")[1])
    source_chat_id = get_source_chat_id(user_id)
    if source_chat_id is None:
        bot.send_message(user_id, "Ожидайте, идет уточнение чата администраторами.")
        return
    now = datetime.now().isoformat()
    try:
        house_id = get_house_id_by_chat_id(DB_FILE, source_chat_id)
        mark_user_date_del_by_tg_and_house(DB_FILE, user_id, house_id, now)
        application_id = update_latest_application_status_by_tg_and_house(
            DB_FILE,
            user_id,
            house_id,
            "denied",
            now,
            decided_at=now,
            decided_by=ADMIN_ID,
        )
        if application_id:
            record_admin_action(DB_FILE, application_id, ADMIN_ID, "deny", None, now)
    except Exception as e:
        logging.error(f"Ошибка обновления записи для {user_id} при отклонении: {e}")
    member = None
    try:
        member = bot.get_chat_member(source_chat_id, user_id)
    except Exception as e:
        logging.error(f"Ошибка проверки участника {user_id} в чате {source_chat_id}: {e}")
    try:
        # Удаляем пользователя из группового чата.
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

# ====================================================================
# Callback-обработчик: запрос нового фото (администратор)
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("request_photo:"))
def request_photo(call):
    """
    Обрабатывает запрос администратора на получение нового фото:
      - Извлекает user_id из callback_data.
      - Обновляет состояние администратора (ожидание ввода причины).
      - Отправляет админу сообщение с просьбой указать причину запроса.
    """
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

# ====================================================================
# Обработчик сообщений от администратора (ввод причины запроса нового фото)
# ====================================================================
@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID and not (message.text and message.text.startswith("/")))
def save_reason(message):
    """
    Сохраняет причину, введённую администратором для запроса нового фото:
      - Проверяет, что администратор находится в режиме ожидания ввода.
      - Сохраняет причину в словаре pending_users для соответствующего пользователя.
      - Отправляет уведомление пользователю с просьбой прислать новое фото.
      - Сбрасывает состояние администратора.
    """
    global admin_state
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
        try:
            house_id = get_house_id_by_chat_id(DB_FILE, src_chat)
            application_id = update_latest_application_status_by_tg_and_house(
                DB_FILE,
                user_id,
                house_id,
                "photo_requested_again",
                datetime.now().isoformat(),
                reason=reason,
                decision_note=reason,
            )
            if application_id:
                record_admin_action(DB_FILE, application_id, ADMIN_ID, "request_photo", reason, datetime.now().isoformat())
        except Exception as e:
            logging.error("Ошибка обновления заявки при request_photo: %s", e)
    else:
        logging.error("src_chat не определён, уведомление не отправлено.")
    # Сбрасываем состояние администратора
    admin_state.pop(ADMIN_ID, None)


# ====================================================================
# Обработчик события выхода участника из чата
# ====================================================================
@bot.message_handler(content_types=['left_chat_member'])
def left_member_handler(message):
    """
    Обрабатывает событие выхода участника:
      - Обновляет поле date_del в записи пользователя для данного чата (дома).
      - Если у пользователя не осталось активных записей (где date_del = NULL), обновляет поле date_del для всех автомобилей.
      - Удаляет данные пользователя из словаря pending_users.
    """
    left_user = message.left_chat_member
    user_id = left_user.id
    now = datetime.now().isoformat()
    logging.info(f"Обработка выхода пользователя {user_id} из чата {message.chat.id} в {now}")
    try:
        # Получаем house_id для текущего чата
        house_id = get_house_id_by_chat_id(DB_FILE, message.chat.id)
        if house_id:
            logging.info(f"Для пользователя {user_id} найден дом: house_id = {house_id} в чате {message.chat.id}")
        else:
            house_id = None
            logging.warning(f"Для чата {message.chat.id} не найден дом (house_id = None)")

        # Обновляем запись для данного чата (только для этого дома)
        mark_user_date_del_by_tg_and_house(DB_FILE, user_id, house_id, now)
        if house_id is not None:
            logging.info(f"Обновлена дата удаления для пользователя {user_id} с house_id = {house_id}")
        else:
            logging.info(f"Обновлена дата удаления для пользователя {user_id} для всех записей (house_id не найден)")

        # Проверяем наличие активных записей (где date_del пустой) для этого пользователя
        active_count = get_active_user_count_by_tg(DB_FILE, user_id)
        logging.info(f"Для пользователя {user_id} осталось {active_count} активных записей в таблице users")
        if active_count == 0:
            # Обновляем поле date_del для всех автомобилей данного пользователя
            # Здесь используется вложенный запрос, который выбирает все id записей пользователя из таблицы users,
            # что позволяет обновить все авто, связанные с этим пользователем.
            mark_cars_date_del_by_tg(DB_FILE, user_id, now)
            logging.info(f"Обновлена дата удаления для всех автомобилей пользователя {user_id}")
    except Exception as e:
        logging.error(f"Ошибка при обработке выхода пользователя {user_id}: {e}")
    if user_id in pending_users:
        del pending_users[user_id]
        logging.info(f"Пользователь {user_id} удалён из pending_users")





# ====================================================================
# Callback-обработчик идентификации (подтверждение проживания)
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == 'identification')
def identification_handler(call):
    """
    Обрабатывает запрос идентификации пользователя:
      - Проверяет, что сообщение имеет корректный чат.
      - Определяет исходный групповой чат.
      - Отправляет пользователю сообщение с кнопками для подтверждения проживания или отказа.
    """
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
    # Формируем две кнопки: подтверждение проживания и отказ.
    confirm_button = InlineKeyboardButton("Живу тут и готов подтвердить", callback_data="confirm_residence")
    not_residing_button = InlineKeyboardButton("Не живу тут", callback_data="not_residing")
    keyboard.add(confirm_button, not_residing_button)
    bot.send_message(call.message.chat.id, "Пожалуйста подтвердите ваше проживание:", reply_markup=keyboard)

# ====================================================================
# Callback-обработчик для пользователей, сообщающих, что не являются жильцами
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "not_residing")
def not_residing_handler(call):
    """
    Обрабатывает выбор пользователя, который сообщает, что он не является жильцом:
      - Отправляет сообщение, что чат предназначен только для жильцов.
      - Обновляет запись пользователя, устанавливая дату удаления.
      - Пытается удалить пользователя из группового чата.
    """
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Чат предназначен только для жильцов.")
    source_id = get_source_chat_id(user_id)
    now = datetime.now().isoformat()
    house_id = get_house_id_by_chat_id(DB_FILE, source_id) if source_id else None
    if house_id is None:
        mark_user_date_del_by_tg_and_house(DB_FILE, user_id, None, now)
        user_record = get_user_id_by_tg_and_null_house(DB_FILE, user_id)
    else:
        mark_user_date_del_by_tg_and_house(DB_FILE, user_id, house_id, now)
        user_record = get_user_id_by_tg_and_house(DB_FILE, user_id, house_id)
    if user_record:
        mark_cars_date_del_by_user_id(DB_FILE, user_record, now)
    if source_id:
        try:
            bot.kick_chat_member(source_id, user_id)
            bot.unban_chat_member(source_id, user_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Ошибка удаления {user_id} из чата {source_id}: {e}")
    bot.answer_callback_query(call.id)

# ====================================================================
# Callback-обработчик для выбора опции "Да" при возвращении в группу
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "return_yes")
def return_yes_handler(call):
    """
    Обрабатывает выбор пользователя, который хочет вернуться в группу:
      - Сбрасывает дату удаления и обновляет дату регистрации.
      - Просит пользователя отправить актуальное фото дворовой территории.
    """
    user_id = call.from_user.id
    # now = datetime.now().isoformat()
    # conn = sqlite3.connect(DB_FILE)
    # cursor = conn.cursor()
    # cursor.execute("UPDATE users SET date_del = NULL, date_add = ? WHERE tg_id = ?", (now, user_id))
    # conn.commit()
    # conn.close()
    bot.send_message(call.message.chat.id, "Отлично! Пожалуйста отправьте АКТУАЛЬНУЮ фотографию дворовой территории из окна Вашей квартиры.")
    user_state[user_id] = "awaiting_photo"
    bot.answer_callback_query(call.id)

# ====================================================================
# Callback-обработчик для выбора опции "Нет" при возвращении в группу
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "return_no")
def return_no_handler(call):
    """
    Обрабатывает выбор пользователя, который отказывается возвращаться в группу.
      - Отправляет прощальное сообщение.
    """
    bot.send_message(call.message.chat.id, "Ну, заходи если чё...")
    bot.answer_callback_query(call.id)

# ====================================================================
# Callback-обработчик подтверждения проживания
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "confirm_residence")
def confirm_residence_handler(call):
    """
    Обрабатывает подтверждение проживания пользователя:
      - Определяет дом по исходному чату.
      - Если пользователь уже зарегистрирован и подтверждён, уведомляет его или предлагает вернуться в группу.
      - Если запись отсутствует, запускается процесс регистрации (опрос).
    """
    user_id = call.from_user.id
    source_chat = get_source_chat_id(user_id)
    house_id = get_house_id_by_chat_id(DB_FILE, source_chat) if source_chat else None
    user_record = get_user_full_record_by_tg_and_house(DB_FILE, user_id, house_id)
    if user_record:
        if not user_record[2] or user_record[2].strip() == "":
            bot.send_message(call.message.chat.id, f"{user_record[1]}, мы тебя узнали и ты уже зарегистрирован.")
            bot.answer_callback_query(call.id)
            return
        else:
            keyboard = InlineKeyboardMarkup(row_width=2)
            yes_button = InlineKeyboardButton("Да", callback_data="return_yes")
            no_button = InlineKeyboardButton("Нет", callback_data="return_no")
            keyboard.add(yes_button, no_button)
            bot.send_message(call.message.chat.id, f"Привет {user_record[1]}! Хотите вернуться в группу?", reply_markup=keyboard)
            bot.answer_callback_query(call.id)
            return
    else:
         bot.send_message(call.message.chat.id, "Ответьте на несколько вопросов, пожалуйста. Данные на серверах хранятся в зашифрованном виде.")
         registration.ask_name(call.message.chat.id, user_id)
         bot.answer_callback_query(call.id)


# ====================================================================
# Обработчик команды /db для администратора (вывод содержимого таблиц)
# ====================================================================
@bot.message_handler(commands=['db'])
def db_handler(message):
    """
    Выводит содержимое таблиц houses, users и cars для администратора.
    Ограничивает доступ к этой команде, если пользователь не является администратором.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа")
        return
    output = dump_tables_text(DB_FILE)
    max_length = 4096
    # Если вывод слишком длинный, отправляем его порциями.
    for i in range(0, len(output), max_length):
        bot.send_message(message.chat.id, output[i:i+max_length])


def send_chunked_report(chat_id, report):
    max_length = 4096
    if not report:
        bot.send_message(chat_id, "Нет данных.")
        return
    for i in range(0, len(report), max_length):
        bot.send_message(chat_id, report[i:i + max_length])


# ====================================================================
# Обработчик команды /pending для администратора
# ====================================================================
@bot.message_handler(commands=['pending'])
def pending_handler(message):
    """
    Показывает администратору текущие pending-заявки из памяти.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    if not pending_users:
        bot.send_message(message.chat.id, "Нет pending-заявок.")
        return

    report_lines = ["Pending-заявки:"]
    for user_id in sorted(pending_users):
        data = pending_users[user_id]
        source_chat = data.get("source_chat_id", "не указан")
        status = data.get("status", "не указан")
        reason = data.get("reason")
        join_time = data.get("join_time")
        join_time_text = join_time.isoformat() if hasattr(join_time, "isoformat") else str(join_time) if join_time else "не указано"
        line = f"- user {user_id}: чат {source_chat}, статус {status}, вход {join_time_text}"
        if reason:
            line += f", причина: {reason}"
        report_lines.append(line)
    send_chunked_report(message.chat.id, "\n".join(report_lines))


# ====================================================================
# Обработчик команды /users для администратора
# ====================================================================
@bot.message_handler(commands=['users'])
def users_handler(message):
    """
    Показывает активных пользователей по указанной группе.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Укажите ID группы, например: /users -123456789")
        return
    group_id_check = parts[1]
    try:
        house_id = get_house_id_by_chat_id(DB_FILE, group_id_check)
        if not house_id:
            bot.send_message(message.chat.id, f"Для группы {group_id_check} не найден дом в базе.")
            return
        users_rows = get_active_user_rows_by_house(DB_FILE, house_id)
        if not users_rows:
            bot.send_message(message.chat.id, f"В группе {group_id_check} нет активных пользователей.")
            return
        report_lines = [f"Активные пользователи группы {group_id_check}:"]
        for tg_id, name, surname, apartment, phone, date_add in users_rows:
            report_lines.append(
                f"- кв. {apartment or 'не указана'}: {name or 'без имени'} {surname or ''}".strip()
                + f" (tg_id={tg_id}, phone={phone or 'не указан'})"
            )
        send_chunked_report(message.chat.id, "\n".join(report_lines))
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")


# ====================================================================
# Обработчик команды /apartment для администратора
# ====================================================================
@bot.message_handler(commands=['apartment'])
def apartment_handler(message):
    """
    Ищет активных пользователей по номеру квартиры в указанной группе.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(message.chat.id, "Укажите ID группы и номер квартиры, например: /apartment -123456789 12")
        return
    group_id_check = parts[1]
    apartment = parts[2].strip()
    try:
        house_id = get_house_id_by_chat_id(DB_FILE, group_id_check)
        if not house_id:
            bot.send_message(message.chat.id, f"Для группы {group_id_check} не найден дом в базе.")
            return
        users_rows = search_active_user_rows_by_apartment(DB_FILE, house_id, apartment)
        if not users_rows:
            bot.send_message(message.chat.id, f"В группе {group_id_check} не найдено активных пользователей в квартире {apartment}.")
            return
        report_lines = [f"Квартира {apartment} в группе {group_id_check}:"]
        for tg_id, name, surname, apartment_value, phone, date_add in users_rows:
            report_lines.append(
                f"- {name or 'без имени'} {surname or ''}".strip()
                + f" (tg_id={tg_id}, phone={phone or 'не указан'})"
            )
        send_chunked_report(message.chat.id, "\n".join(report_lines))
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")

# ====================================================================
# Обработчик команды /check для администратора (проверка регистрации в указанном чате)
# ====================================================================
# TODO Нужно переписать check так, чтобы он мониторил в УКАЗАННОМ чате новые сообщения и если сообщение от пользователя, которого нет в БД нужно его блокировать и предлагать ему пройти регистрацю с подтверждением.
#
@bot.message_handler(commands=['check'])
def check_handler(message):
    """
    Проверяет регистрацию пользователей в указанном групповом чате:
      - По ID группы (chat_id) находит дом (house) в базе.
      - Из таблицы users извлекает активных пользователей (без даты удаления).
      - Отправляет администратору список зарегистрированных пользователей.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Укажите ID группы, например: /check -123456789")
        return
    group_id_check = parts[1]
    try:
        house_id = get_house_id_by_chat_id(DB_FILE, group_id_check)
        if not house_id:
            bot.send_message(message.chat.id, f"Для группы {group_id_check} не найден дом в базе.")
            return
        users_in_house = get_active_user_tg_ids_by_house(DB_FILE, house_id)
        if not users_in_house:
            bot.send_message(message.chat.id, f"В группе {group_id_check} нет зарегистрированных пользователей.")
        else:
            tg_ids = [str(row[0]) for row in users_in_house]
            bot.send_message(message.chat.id, f"В группе {group_id_check} зарегистрировано {len(tg_ids)} пользователей: {', '.join(tg_ids)}")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")

# ====================================================================
# Обработчик команды /checkall для администратора (проверка регистрации во всех группах)
# ====================================================================
# TODO Нужно переписать checkall так, чтобы он мониторил во всех чатах из таблицы houses новые сообщения и если сообщение от пользователя, которого нет в БД нужно его блокировать и предлагать ему пройти регистрацю с подтверждением.
#
@bot.message_handler(commands=['checkall'])
def checkall_handler(message):
    """
    Извлекает все дома (группы) из таблицы houses и для каждой группы определяет количество активных пользователей.
    Формирует отчет и отправляет его администратору.
    """
    if message.from_user.id != int(ADMIN_ID):
        bot.send_message(message.chat.id, "Нет доступа.")
        return
    try:
        houses_list = get_active_house_rows(DB_FILE)
        report = ""
        for chat_id, house_id in houses_list:
            count = count_active_users_by_house(DB_FILE, house_id)
            report += f"Группа {chat_id}: зарегистрировано {count} пользователей\n"
        if report == "":
            report = "Нет данных по группам."
        bot.send_message(message.chat.id, report)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при проверке: {e}")

# ====================================================================
# Обработчики подтверждения регистрации
# ====================================================================
@bot.callback_query_handler(func=lambda call: call.data == "confirm_registration_yes")
def confirm_registration_yes_handler(call):
    """
    Если пользователь соглашается на регистрацию, запускается полный процесс опроса.
    """
    user_id = call.from_user.id
    registration.ask_name(call.message.chat.id, user_id)
    bot.answer_callback_query(call.id, "Начинаем регистрацию")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_registration_no")
def confirm_registration_no_handler(call):
    """
    Если пользователь отказывается от регистрации, отправляется уведомление и происходит его удаление из чата.
    """
    user_id = call.from_user.id
    bot.send_message(call.message.chat.id, "Чат предназначен только для жителей дома. Сейчас мы вас из него удалим.")
    source = get_source_chat_id(user_id)
    if source:
         try:
              bot.kick_chat_member(source, user_id)
              bot.unban_chat_member(source, user_id)
              bot.send_message(source, f"Пользователь {call.from_user.first_name} отказался от регистрации и удалён из чата.")
         except Exception as e:
              logging.error(f"Ошибка удаления пользователя {user_id} из чата {source}: {e}")
    bot.answer_callback_query(call.id, "Вы удалены из чата")

# ====================================================================
# Запуск бота
# ====================================================================
# Запускаем постоянное прослушивание входящих сообщений (polling) от Telegram.
while True:
    try:
        bot.polling()
    except RequestException as e:
        logging.error("Не удалось подключиться к Telegram API: %s", e.__class__.__name__)
        time.sleep(30)
