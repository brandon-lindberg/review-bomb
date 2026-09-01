"""`python -m app` must exit with the status the CLI returns.

The scheduled data pipeline chains several `python -m app ...` commands in one
shell step. If the module entrypoint drops the return value, a command that
fails and returns 1 still exits 0, the shell keeps going, and the workflow
reports success on a pipeline that never finished its later stages.
"""

import runpy

import pytest

import app.cli


def _run_module_entrypoint() -> int:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("app", run_name="__main__", alter_sys=True)
    code = excinfo.value.code
    return 0 if code is None else code


def test_module_entrypoint_propagates_failure_exit_code(monkeypatch):
    monkeypatch.setattr(app.cli, "main", lambda: 1)

    assert _run_module_entrypoint() == 1


def test_module_entrypoint_exits_zero_on_success(monkeypatch):
    monkeypatch.setattr(app.cli, "main", lambda: 0)

    assert _run_module_entrypoint() == 0


def test_module_entrypoint_treats_none_as_success(monkeypatch):
    """Several commands fall off the end without an explicit return."""
    monkeypatch.setattr(app.cli, "main", lambda: None)

    assert _run_module_entrypoint() == 0
