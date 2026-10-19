# Changelog

This project follows Keep a Changelog and Semantic Versioning.

`PROJECT_SPEC.md` remains the living implementation plan and progress tracker.

Current baseline tag: `v0.2.0`.
Next planned release: `v0.2.1`.
Release versions follow semantic versioning (`MAJOR.MINOR.PATCH`).

## [Unreleased]

### Added
- `applications` and `admin_actions` SQLite tables: the bot records each access application and every admin decision (`allow`, `deny`, `request_photo`).
- Read-only web dashboard `webapp/app.py` (`python -m webapp.app`, service `residentchatbot-web.service`): totals, recent and pending applications, admin action history, bot service status, public `/health`.
- `WEB_*` settings in `config.py` and `.env.example`.
- Tests for the application repository helpers and the web dashboard.

### Security
- Every dashboard page that shows resident data requires HTTP Basic auth; an empty `WEB_ADMIN_PASSWORD` denies all access.
- `WEB_BIND_HOST` defaults to `127.0.0.1`; credentials are compared with `hmac.compare_digest`.

### Planned
- Stage 8 admin work that is not yet released:
  - resend application;
  - block user;
  - optional rejection comment.

## [v0.2.0] - 2026-05-22

### Added
- Centralized configuration loader in `config.py`.
- SQLite repository layer in `repositories/db.py`.
- Regression tests with `pytest`.
- Admin report commands:
  - `/pending`
  - `/users <chat_id>`
  - `/apartment <chat_id> <apartment>`
- Versioning policy and release protocol in `PROJECT_SPEC.md`.

### Changed
- `main.py` now uses centralized config and repository helpers instead of direct SQL in most handlers.
- `README.md` now reflects the current runbook, commands, and manual verification steps.
- `PROJECT_SPEC.md` now tracks the implementation plan, progress board, progress log, and release policy.
- `CHANGELOG.md` now documents release history separately from the living plan.
- The live bot continues to use proxy, `systemd`, and the same registration flow.

### Fixed
- A regression in the new-house registration path was corrected by using the correct registration profile helper.

### Verified
- Local test suite: `12 passed`.
- Coverage: approximately `94%` total.
- Production service remained `active` after syncs and restarts.

### Notes
- This release is the first formal `semver` baseline after the initial working MVP tag `v0.1.0`.
- It includes operational, documentation, test, and admin-report improvements without changing the core registration flow.

## 2026-05-22 - Current MVP baseline and production inventory

### Added
- Baseline documentation of the working bot:
  - current launch paths;
  - production service name;
  - SQLite storage location;
  - proxy behavior;
  - manual registration flow.
- Safe configuration template in `.env.example`.
- Initial `README.md` with setup, commands, tests, and manual flow check.
- `AGENTS.md` rules for safe work in this repository.

### Changed
- The project was explicitly classified as a partially working MVP, not a greenfield rewrite.
- The documentation began to track production constraints:
  - do not break registration;
  - do not break admin callbacks;
  - do not change SQLite or proxy behavior without backup.

### Notes
- This phase established the practical baseline for all later changes.
- It did not change the user flow.

## 2026-05-22 - Safe configuration and logging

### Added
- `LOG_LEVEL` support with a safe default.
- Explicit `ADMIN_ID` validation at startup.
- Startup logging that reports database path, proxy state, and log level.
- Suppression of noisy `urllib3` logs.
- Centralized config module `config.py`.

### Changed
- `main.py` now reads configuration through `config.py`.
- `README.md` and `.env.example` were updated to document the new config contract.
- The service startup log became consistent and production-friendly.

### Verified
- Local syntax checks passed.
- Production service restarted successfully.
- Proxy remained enabled only for the bot process.

### Notes
- No business logic changed.
- No SQLite schema change was introduced.

## 2026-05-22 - SQLite repository layer

### Added
- `repositories/` package.
- `repositories/db.py` as the shared SQLite helper layer.
- Helpers for:
  - connection handling;
  - schema initialization;
  - read operations on `houses`, `users`, and `cars`;
  - write operations for user and car data;
  - report generation for `/db`.

### Changed
- SQLite table creation moved out of `main.py` into the repository layer.
- Repeated SQL fragments were gradually replaced with repository helpers.
- The live bot remained compatible with the existing SQLite schema.

### Fixed
- A regression introduced during the repository split was corrected:
  - existing users registering in a new house now reuse the correct registration profile helper.

### Verified
- `main.py`, `registration.py`, `config.py`, and `repositories/db.py` compiled successfully.
- The production service restarted cleanly after each sync.

### Notes
- The schema itself was not rewritten.
- The goal was separation of concerns, not a data-model rewrite.

## 2026-05-22 - Test infrastructure and regression coverage

### Added
- `pytest` dependency.
- Test helpers and fakes for the Telegram bot.
- SQLite-backed unit tests.
- Registration-flow tests.
- Validation tests for:
  - names;
  - surnames;
  - apartments;
  - phones;
  - car counts;
  - car numbers.
- Admin-flow tests.
- Status-transition tests.
- Repeat-callback tests.
- Exception-branch tests.

### Changed
- The repository now has a working local regression suite.
- Coverage moved from a minimal smoke-check to a substantial unit-test baseline.

### Verified
- `python -m pytest` passes.
- Coverage reached approximately `94%`.
- The production bot was synced after the test suite changes and stayed healthy.

### Notes
- Tests were intentionally written to avoid changing production behavior.
- The suite focuses on protecting the current flow rather than redesigning it.

## 2026-05-22 - Admin reporting enhancements

### Added
- `/pending` for listing in-memory pending requests.
- `/users` for listing active users in a selected house.
- `/apartment` for searching active users by apartment.
- Repository helpers for active-user and apartment-based reports.

### Changed
- `README.md` was updated with the new admin command list.
- `PROJECT_SPEC.md` was updated to reflect the start of the admin-improvement phase.

### Verified
- Admin-report commands pass unit tests.
- The bot was synced to production and the service was restarted successfully.

### Notes
- These commands improve observability for the administrator.
- They do not alter registration behavior.

## 2026-05-22 - Production synchronization and service checks

### Added
- Repeated production backups before deployment steps.
- Repeated service checks after syncs.
- Journal-based verification of clean startup.

### Changed
- The server copy of the bot was kept aligned with the local working branch.

### Verified
- `residentchatbot.service` stayed `active`.
- Startup logs consistently showed:
  - `proxy=enabled`
  - `log_level=INFO`

### Notes
- The production bot remains the source of truth for operational behavior.
- Manual end-to-end checks were used where automated coverage was still incomplete.

## 2026-05-22 - Project documentation and living plan

### Added
- A detailed `PROJECT_SPEC.md` describing:
  - current status;
  - realized functionality;
  - production-ready parts;
  - fragile areas;
  - incomplete items;
  - implementation plan;
  - progress board;
  - progress log.
- Stage-based implementation tracking.

### Changed
- The project is now tracked as a living plan instead of an ad-hoc codebase.
- Every major stage is reflected in the progress log and status board.

### Notes
- `PROJECT_SPEC.md` is the authoritative implementation plan.
- `CHANGELOG.md` is the visible history of changes.

## Format notes

- `PROJECT_SPEC.md` documents the current plan, risks, and stage-by-stage progress.
- `CHANGELOG.md` documents what changed and when it changed.
- When a change is deployed to production, it should be reflected in both places if it affects the runtime or operating model.
