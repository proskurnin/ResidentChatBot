# AGENTS.md

## 1. Project Context

This repository contains a Python Telegram bot for a private residential building chat.

The bot is used to register residents, collect user details, request photo proof of residence, send applications to an administrator, and allow or deny access to the private house chat.

Important: this project is already running on a server and may be used in real operation.

The project is currently a working MVP / early prototype, not a fully polished production system. Because it is already deployed, all changes must be treated as production-sensitive.

Before making any changes, AI agents must read:

1. `PROJECT_SPEC.md` — the main product and technical specification.
2. `README.md` — setup and usage instructions, if present.
3. `main.py` — current entry point.
4. `registration.py` — current registration flow.
5. `.env.example` — configuration example, if present.
6. Existing systemd/deployment notes, if present.
7. Existing migrations or SQLite initialization code, if present.

`PROJECT_SPEC.md` is the main source of product requirements.  
`AGENTS.md` defines how AI agents must work with this repository.

---

## 2. Production Status

This bot is not just a local experiment.

It is already deployed on a server and runs as a `systemd` service.  
It uses SQLite for data storage and may contain real resident data.  
It may depend on proxy settings to access the Telegram Bot API.

Because of this, AI agents must be conservative.

Before any code change, agents must understand:

- where the bot runs;
- how it starts;
- which systemd service is used;
- where `.env` is located;
- where SQLite database is located;
- whether the database contains production data;
- how proxy is configured;
- how logs are checked;
- how to restart the service;
- how to roll back safely.

Do not assume that local behavior is enough.  
Changes must be safe for a running server deployment.

---

## 3. Current Project Structure

Current core files may include:

- `main.py` — entry point, bot initialization, polling loop, command/callback handlers.
- `registration.py` — multi-step registration flow and helper callbacks.
- `requirements.txt` — runtime dependencies.
- `.env` — local/private configuration. Must not be committed.
- `.env.example` — safe example configuration, if present.
- `database.db` or another SQLite file — local/production database. Must not be committed.
- `PROJECT_SPEC.md` — main technical specification.
- `AGENTS.md` — AI agent operating rules.

The current project is small, but should gradually move toward a clearer structure:

```text
project/
  main.py
  config.py
  requirements.txt
  .env.example
  README.md
  PROJECT_SPEC.md
  AGENTS.md

  bot/
    handlers/
    keyboards/
    messages/

  services/

  repositories/

  models/

  migrations/

  tests/
```

Do not create this whole structure at once unless the task explicitly requires it.  
Refactor gradually and safely.

---

## 4. Existing Functionality

The bot already supports the basic flow:

- `/start`;
- starting registration;
- collecting resident details step by step;
- collecting first name, last name, apartment number, phone, and cars;
- requesting a photo as proof of residence;
- sending the application to an administrator;
- admin actions:
  - allow access;
  - deny access;
  - request a new photo;
- checking users by house;
- storing data in SQLite;
- running on a server via `systemd`;
- using a proxy for Telegram API access.

Do not break the existing working flow.

---

## 5. Main Rule

Do not rewrite the project from scratch unless explicitly instructed.

All changes must be:

- small;
- safe;
- reviewable;
- easy to test manually;
- compatible with the current working MVP;
- safe for the running server deployment.

Priority order:

1. Preserve current production behavior.
2. Document the current server and application state.
3. Add backup and rollback instructions.
4. Improve configuration and logging.
5. Separate database access from Telegram handlers.
6. Formalize registration states.
7. Move business logic into service modules.
8. Add tests for key flows.
9. Only then add new features.

---

## 6. Production Safety Rules

This bot is already running on a server and may be used in real operation.

Before changing code, agents must treat the current behavior as production behavior.

Rules:

- do not break the current registration flow;
- do not change SQLite schema without migration and backup plan;
- do not change systemd behavior without explicit approval;
- do not change proxy behavior without explicit approval;
- do not rename or move the production database without explicit approval;
- do not change callback formats unless backward compatibility is handled;
- do not remove existing admin actions;
- do not change `.env` variable names without compatibility handling;
- do not change the bot token loading mechanism without compatibility handling;
- do not change Telegram polling behavior without clear verification;
- do not commit `.env`, production database files, logs, or resident personal data.

Before any risky change, prepare:

1. backup plan;
2. rollback plan;
3. manual verification checklist;
4. list of affected files;
5. explanation of database impact;
6. explanation of configuration impact;
7. explanation of server/systemd impact.

Recommended server checks before deployment:

```bash
systemctl status <service-name>
journalctl -u <service-name> -n 100 --no-pager
cp <database-path> <database-path>.backup-$(date +%Y%m%d-%H%M%S)
python -m compileall .
```

Recommended checks after deployment:

```bash
systemctl restart <service-name>
systemctl status <service-name>
journalctl -u <service-name> -n 100 --no-pager
```

A change is not complete until the bot starts successfully and the main registration/admin flow is manually verified.

---

## 7. Server Inventory Before Changes

Before the first production-sensitive task, agents must ask the user to confirm or must document if already known:

- server path of the project;
- systemd service name;
- Python version on the server;
- virtual environment path, if any;
- `.env` path;
- SQLite database path;
- log access method;
- current deployment method;
- Git branch used on the server;
- whether the server working tree has uncommitted changes;
- backup location;
- rollback procedure.

If this information is not available, do not make risky assumptions.  
For documentation-only changes, it is acceptable to proceed, but mark unknown server details as `TODO`.

---

## 8. Backup Rules

Before changing production code or database schema, create a backup plan.

For SQLite, recommended backup command:

```bash
cp <database-path> <database-path>.backup-$(date +%Y%m%d-%H%M%S)
```

For code, recommended safety checks:

```bash
git status
git branch --show-current
git log --oneline -5
```

If the production server has uncommitted changes, do not overwrite them blindly.

Recommended code backup options:

```bash
git diff > before-change.patch
git status --short
```

or create a temporary safety branch:

```bash
git checkout -b backup/before-change-$(date +%Y%m%d-%H%M%S)
```

Use the approach that fits the project workflow.

Never delete production database files.  
Never replace production `.env` without explicit approval.

---

## 9. Rollback Rules

Every risky change must include a rollback plan.

Rollback plan must explain:

- how to restore previous code;
- how to restore SQLite database if changed;
- how to restart the systemd service;
- how to verify that the bot is working again.

Typical rollback commands may include:

```bash
git status
git checkout -- <changed-files>
systemctl restart <service-name>
systemctl status <service-name>
journalctl -u <service-name> -n 100 --no-pager
```

If database schema was changed, rollback must be planned before the change.  
Do not apply irreversible migrations without explicit approval.

---

## 10. Build, Run, and Development Commands

There is no separate build system or packaged release process.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run locally:

```bash
python main.py
```

Quick syntax check:

```bash
python -m compileall .
```

If tests are added, use:

```bash
python -m pytest
```

Tests should be placed under `tests/` and named as `test_*.py`.

Server service commands, once the service name is known:

```bash
systemctl status <service-name>
systemctl restart <service-name>
journalctl -u <service-name> -n 100 --no-pager
journalctl -u <service-name> -f
```

---

## 11. Coding Style

Follow the existing Python style:

- Python 3.10+;
- 4-space indentation;
- `snake_case` for functions, variables, handlers, and modules;
- clear descriptive names for handlers and service functions;
- small functions are preferred over large inline blocks;
- keep Russian user-facing bot messages consistent and clear;
- do not mix unrelated logic inside Telegram handlers.

No formatter or linter is configured yet.  
Keep edits consistent with surrounding code.

---

## 12. Architecture Direction

The project should gradually move toward separation of responsibilities.

### `main.py`

Should eventually contain only:

- configuration loading;
- bot initialization;
- database initialization;
- handler registration;
- polling startup.

Avoid adding new business logic directly to `main.py`.

### `bot/handlers`

Telegram-specific code:

- command handlers;
- message handlers;
- callback handlers.

Handlers should receive Telegram events, call services, and send responses.

### `services`

Business logic:

- registration workflow;
- admin decisions;
- user status changes;
- notification preparation;
- validation orchestration.

### `repositories`

Database access:

- SQL queries;
- user CRUD;
- house CRUD;
- car CRUD;
- admin action history.

Telegram-specific code must not be placed in repositories.

### `bot/messages`

User-facing message texts.

### `bot/keyboards`

Inline and reply keyboard builders.

---

## 13. Registration Flow Rules

Registration is the most important user flow.

When changing registration logic, always verify the full path:

1. User sends `/start`.
2. Bot starts registration.
3. User enters first name.
4. User enters last name.
5. User enters apartment number.
6. User enters phone number.
7. User enters car information or says there is no car.
8. User sends a photo.
9. Application is sent to the administrator.
10. Administrator selects allow, deny, or request new photo.
11. User receives the final result.

Registration states should gradually become explicit and persistent.

Recommended registration steps:

- `waiting_first_name`
- `waiting_last_name`
- `waiting_flat_number`
- `waiting_phone`
- `waiting_cars`
- `waiting_photo`
- `waiting_admin_decision`
- `completed`

Avoid relying only on in-memory dictionaries for critical state.  
If state is needed after restart, it must be stored in SQLite.

Because the bot is already running on a server, state migration must be handled carefully.  
Do not change state names or callback formats without compatibility checks.

---

## 14. User Status Rules

Use explicit user statuses where possible.

Recommended statuses:

- `new`
- `registration_in_progress`
- `photo_required`
- `pending_review`
- `photo_requested_again`
- `approved`
- `denied`
- `blocked`

Status changes should be saved to the database.

If the current database uses different status names, do not rename them blindly.  
Add compatibility logic or a migration plan.

---

## 15. Admin Rules

Admin functionality must be protected.

Requirements:

- check administrator Telegram ID before executing admin commands;
- check administrator Telegram ID before processing admin callbacks;
- never allow a normal user to trigger `allow`, `deny`, or `request photo`;
- handle repeated button clicks safely;
- check that the target user exists;
- check that the application status is still valid;
- log admin actions.

Recommended callback format:

```text
approve:{user_id}
deny:{user_id}
request_photo:{user_id}
```

If the existing project uses another format, do not break it without a migration plan.

---

## 16. Database Rules

The current database is SQLite.

Rules:

- do not commit `database.db`;
- do not commit production database dumps;
- do not commit files that contain personal data of residents;
- do not store SQL directly in new Telegram handlers;
- move SQL gradually into repository modules;
- do not remove existing columns without explicit approval;
- preserve existing data when changing schema.

If the schema changes, add a migration under `migrations/`.

Recommended migration naming:

```text
001_initial.sql
002_add_registration_step.sql
003_add_admin_actions.sql
```

If migrations are not implemented yet, explain the required manual database change clearly.

For production database changes:

1. identify the exact database file path;
2. create backup;
3. document migration;
4. test on a copy if possible;
5. apply only after explicit approval;
6. verify bot startup and core flow after migration.

---

## 17. Configuration and Secrets

Configuration is loaded from `.env`.

Never commit:

- `.env`;
- bot token;
- proxy URL with login/password;
- real production admin IDs if they are considered private;
- production database;
- personal data of residents;
- chat invite links;
- logs with personal data or secrets.

Use `.env.example` for safe examples only.

Recommended environment variables:

```env
BOT_TOKEN=
DATABASE_PATH=
ADMIN_IDS=
ADMIN_CHAT_ID=
DEFAULT_HOUSE_ID=
HTTP_PROXY=
HTTPS_PROXY=
LOG_LEVEL=INFO
```

Do not print secrets in logs.

If existing `.env` variable names differ, preserve backward compatibility.

---

## 18. Proxy Rules

The bot may require a proxy to access Telegram API from the server.

Rules:

- preserve proxy support;
- read proxy settings from `.env`;
- log only whether proxy is enabled or disabled;
- do not log full proxy credentials;
- handle Telegram API connection errors clearly;
- do not remove or rename proxy environment variables without compatibility handling.

Because the production server may depend on proxy, proxy-related changes are risky and require explicit verification.

---

## 19. Logging Rules

Use safe and useful logging.

Log:

- bot startup;
- configuration loading result;
- database initialization;
- whether proxy is enabled;
- registration start;
- registration step changes;
- photo received;
- application sent to admin;
- admin decisions;
- Telegram API errors;
- database errors;
- unexpected exceptions.

Do not log:

- bot token;
- full proxy URL with password;
- full `.env` contents;
- unnecessary personal data;
- production secrets.

Logs must help diagnose production problems without leaking sensitive data.

---

## 20. Testing Guidelines

There is no automated test suite in the repository today.

Validate changes manually by:

- running the bot locally;
- exercising the affected Telegram flow;
- checking that SQLite data is written as expected;
- checking admin callbacks;
- checking logs.

If tests are introduced, prefer `pytest`.

Priority test areas:

- phone validation;
- registration step transitions;
- user creation;
- status updates;
- admin allow/deny/request photo;
- callback from non-admin user;
- repeated admin callback clicks;
- database updates.

For production deployment, manual verification is required even if tests pass.

---

## 21. Manual Verification Checklist

After any production-relevant change, verify:

- service starts successfully;
- `/start` works;
- registration starts correctly;
- each registration step works;
- phone validation works;
- photo upload works;
- admin receives the application;
- admin can approve;
- admin can deny;
- admin can request a new photo;
- user receives the correct result;
- data is saved to SQLite;
- logs do not contain secrets;
- proxy still works;
- no unexpected errors appear in `journalctl`.

---

## 22. Commit and Pull Request Guidelines

Keep commits small and action-oriented.

Good examples:

```text
Add config loader
Move user SQL to repository
Add registration status field
Fix request photo callback
Document production rollback plan
```

Pull requests or change summaries should include:

- what changed;
- affected files;
- user-visible behavior;
- configuration impact;
- database impact;
- server/systemd impact;
- how it was tested;
- risks or follow-up work.

---

## 23. Required Response Format After Changes

After making changes, AI agents must respond with:

```text
What changed:
- ...

Files changed:
- ...

How to verify:
- ...

Risks:
- ...
```

If the database schema changed, also include:

```text
Database changes:
- ...

Migration required:
- yes/no

Backup required:
- yes/no
```

If the change affects configuration, also include:

```text
Configuration changes:
- ...
```

If the change affects server deployment, also include:

```text
Server/deployment impact:
- ...

Rollback:
- ...
```

---

## 24. Required Plan Before Risky Changes

Before making risky changes, AI agents must provide a production-safe plan.

The plan must include:

```text
Planned changes:
- ...

Files to change:
- ...

Business logic impact:
- yes/no

Registration flow impact:
- yes/no

Database impact:
- yes/no

Configuration impact:
- yes/no

Systemd/deployment impact:
- yes/no

Backup plan:
- ...

Rollback plan:
- ...

Manual verification checklist:
- ...
```

Risky changes include:

- registration flow changes;
- callback format changes;
- database schema changes;
- `.env` variable changes;
- proxy changes;
- systemd changes;
- dependency upgrades;
- restructuring core files;
- changes to admin approval/denial behavior.

---

## 25. Safe Refactoring Plan

Recommended order of work:

0. Production inventory:
   - document service name;
   - document server path;
   - document `.env` path;
   - document database path;
   - document logs and restart commands;
   - document backup and rollback steps.

1. Document current behavior.

2. Add or update `README.md`.

3. Add or update `.env.example`.

4. Create `config.py` while preserving current `.env` compatibility.

5. Add safe logging.

6. Move SQL into repository modules without changing behavior.

7. Formalize user statuses and registration steps with compatibility handling.

8. Move business logic into services.

9. Move messages and keyboards into separate modules.

10. Add tests.

11. Improve admin commands.

12. Prepare production deployment notes.

Do not perform all steps in a single large change.

---

## 26. Documentation Requirements

The repository should document:

- project purpose;
- current deployment status;
- local run instructions;
- production run instructions;
- systemd service usage;
- `.env` variables;
- SQLite database location/configuration;
- backup steps;
- rollback steps;
- manual verification checklist;
- user commands;
- admin commands;
- known technical debt;
- planned refactoring steps.

If exact production details are not known, use `TODO` placeholders instead of guessing.

---

## 27. Definition of Done

A change is complete only if:

- the bot starts successfully;
- the main registration flow still works;
- photo upload still works;
- the application is sent to the administrator;
- admin allow/deny/request photo still works;
- data is saved to SQLite;
- proxy behavior is preserved;
- secrets are not logged;
- `.env` and database files are not committed;
- manual verification steps are documented;
- database changes include a migration or clear manual instructions;
- risky changes include backup and rollback notes.

---

## 28. Final Principle

This is already a working server-side bot.

The goal is not to make it perfect in one step.  
The goal is to make it safer, clearer, more testable, and easier to develop without breaking the current working production behavior.

First: preserve and document.  
Then: refactor safely.  
Only after that: add new features.
