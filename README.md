# ResidentChatBot

Telegram-бот для закрытого домового чата. Бот проводит пользователя через регистрацию, собирает анкету, принимает фото-подтверждение проживания и передает заявку администратору на решение о доступе.

## Current launch

- Local run: `python main.py`
- On the server: `systemd` service `residentchatbot.service`
- Config: `.env`
- Storage: local SQLite database `database.db`

The bot currently uses a proxy for Telegram API access when it is configured in the service environment.

## Setup

1. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Create `.env` from `.env.example`.
3. Start the bot locally:
   ```bash
   python main.py
   ```

## Tests

Run the current regression checks with:

```bash
python -m pytest
```

## Environment variables

- `API_TOKEN` - Telegram bot token from BotFather.
- `ADMIN_ID` - Telegram user ID of the administrator.
- `BOT_NAME` - bot username without `@`.
- `LOG_LEVEL` - optional logging level, for example `INFO` or `WARNING`.
- `HTTP_PROXY` / `HTTPS_PROXY` - optional, for server-side Telegram access.

Configuration is now loaded centrally from `config.py`, which reads `.env` when present and keeps systemd `EnvironmentFile` values intact.

## Current bot commands

- `/start` - user entry point in a private chat.
- `/newuser` - starts the registration flow.
- `/db` - admin-only dump of database tables.
- `/pending` - admin-only list of pending requests from in-memory state.
- `/users` - admin-only list of active users for a selected house.
- `/apartment` - admin-only search by apartment inside a selected house.
- `/check` - admin-only check for a selected house.
- `/checkall` - admin-only summary across all houses.

The bot also uses inline callback actions for registration, approval, denial, and photo requests.

## Manual flow check

1. Open a private chat with the bot and send `/start`.
2. Start the registration flow from the button menu.
3. Enter first name, last name, apartment number, phone number, and car data if requested.
4. Send the requested photo from the apartment window.
5. Verify that the admin receives the application and photo.
6. As admin, test `allow`, `deny`, and `request new photo` callbacks.
7. Re-open the bot from the same user and confirm that the "already known" path still works.

## Notes

- The project currently stores state partly in memory and partly in SQLite.
- Automated tests are available with `python -m pytest`.
- Future refactoring should move bot handlers, services, and database access into separate modules gradually, without changing the user flow first.
