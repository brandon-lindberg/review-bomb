from app.cli import _is_transient_database_error


def test_is_transient_database_error_matches_recovery_mode_message():
    exc = RuntimeError("the database system is in recovery mode")
    assert _is_transient_database_error(exc) is True


def test_is_transient_database_error_checks_nested_causes():
    try:
        try:
            raise RuntimeError("connection was closed in the middle of operation")
        except RuntimeError as inner:
            raise RuntimeError("top-level batch failure") from inner
    except RuntimeError as exc:
        assert _is_transient_database_error(exc) is True


def test_is_transient_database_error_ignores_non_transient_failure():
    exc = RuntimeError("violates unique constraint")
    assert _is_transient_database_error(exc) is False
