from repositories.db import (
    ensure_house_exists,
    get_application_row_by_id,
    get_dashboard_totals,
    get_latest_application_id_by_tg_and_house,
    get_pending_application_rows,
    get_recent_admin_actions,
    initialize_schema,
    insert_application,
    record_admin_action,
    update_latest_application_status_by_tg_and_house,
)


def add_application(db_file, tg_id, house_id, status="pending_review", created_at="2026-05-22T10:00:00"):
    return insert_application(
        db_file,
        tg_id,
        None,
        house_id,
        10001,
        "Ivan",
        "Petrov",
        "12",
        "+79990000000",
        "photo-1",
        status,
        created_at,
        created_at,
    )


def test_application_lifecycle_and_admin_actions(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_schema(db_file)
    house_id = ensure_house_exists(db_file, 10001, "2026-05-22T10:00:00")

    first_id = add_application(db_file, 555, house_id)
    second_id = add_application(db_file, 555, house_id, created_at="2026-05-22T11:00:00")
    assert get_latest_application_id_by_tg_and_house(db_file, 555, house_id) == second_id

    updated_id = update_latest_application_status_by_tg_and_house(
        db_file,
        555,
        house_id,
        "approved",
        "2026-05-22T12:00:00",
        decided_at="2026-05-22T12:00:00",
        decided_by=42,
    )
    assert updated_id == second_id
    record_admin_action(db_file, second_id, 42, "allow", None, "2026-05-22T12:00:00")

    row = get_application_row_by_id(db_file, second_id)
    assert row[7] == "approved"
    assert row[12] == "2026-05-22T12:00:00"
    assert row[13] == 42
    assert get_application_row_by_id(db_file, first_id)[7] == "pending_review"

    actions = get_recent_admin_actions(db_file)
    assert [(a[1], a[2], a[3]) for a in actions] == [(second_id, 42, "allow")]

    totals = get_dashboard_totals(db_file)
    assert totals["houses_total"] == 1
    assert totals["pending_applications"] == 1
    assert totals["approved_applications"] == 1
    assert totals["denied_applications"] == 0


def test_status_update_keeps_existing_decision_fields(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_schema(db_file)
    house_id = ensure_house_exists(db_file, 10001, "2026-05-22T10:00:00")
    application_id = add_application(db_file, 555, house_id)

    update_latest_application_status_by_tg_and_house(
        db_file, 555, house_id, "photo_requested_again", "2026-05-22T11:00:00", reason="blurry"
    )
    update_latest_application_status_by_tg_and_house(
        db_file, 555, house_id, "denied", "2026-05-22T12:00:00", decided_at="2026-05-22T12:00:00", decided_by=42
    )

    row = get_application_row_by_id(db_file, application_id)
    assert row[7] == "denied"
    assert row[8] == "blurry"


def test_pending_rows_and_missing_application(tmp_path):
    db_file = tmp_path / "test.db"
    initialize_schema(db_file)
    house_id = ensure_house_exists(db_file, 10001, "2026-05-22T10:00:00")

    assert update_latest_application_status_by_tg_and_house(
        db_file, 555, house_id, "approved", "2026-05-22T12:00:00"
    ) is None

    pending_id = add_application(db_file, 555, house_id)
    add_application(db_file, 556, house_id, status="approved")
    no_house_id = add_application(db_file, 557, None, status="photo_requested_again")

    assert get_latest_application_id_by_tg_and_house(db_file, 557, None) == no_house_id
    assert [row[0] for row in get_pending_application_rows(db_file)] == [no_house_id, pending_id]
