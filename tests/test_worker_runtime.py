from app.tasks.runtime import _job_lock_key


def test_job_lock_key_is_stable_and_positive():
    first = _job_lock_key("db_heavy_bulk")
    second = _job_lock_key("db_heavy_bulk")

    assert first == second
    assert first > 0


def test_job_lock_keys_differ_for_different_groups():
    assert _job_lock_key("db_heavy_bulk") != _job_lock_key("source_sync")
