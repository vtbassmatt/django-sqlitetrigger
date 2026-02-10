import pytest
from django.db import connection

import sqlitetrigger
from sqlitetrigger import core


def test_trigger_requires_name():
    with pytest.raises(ValueError, match="must have a name"):
        core.Trigger(when=core.Before, operation=core.Insert)


def test_trigger_requires_when():
    with pytest.raises(ValueError, match="must have a 'when'"):
        core.Trigger(name="t", operation=core.Insert)


def test_trigger_requires_operation():
    with pytest.raises(ValueError, match="must have an 'operation'"):
        core.Trigger(name="t", when=core.Before)


def test_trigger_name_length():
    with pytest.raises(ValueError, match="63 characters"):
        core.Trigger(name="x" * 64, when=core.Before, operation=core.Insert, func="SELECT 1;")


def test_compile_simple(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="test_trigger",
        when=core.Before,
        operation=core.Insert,
        func="SELECT RAISE(ABORT, 'no inserts');",
    )
    stmts = trigger.compile(TestModel)
    assert len(stmts) == 1
    sql = stmts[0]
    assert "CREATE TRIGGER sqlitetrigger_tests_testmodel_test_trigger" in sql
    assert "BEFORE INSERT ON tests_testmodel" in sql
    assert "SELECT RAISE(ABORT, 'no inserts');" in sql


def test_compile_with_condition(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="conditional",
        when=core.After,
        operation=core.Update,
        condition="OLD.int_field != NEW.int_field",
        func="SELECT 1;",
    )
    stmts = trigger.compile(TestModel)
    assert "WHEN (OLD.int_field != NEW.int_field)" in stmts[0]


def test_compile_multi_operation(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="multi",
        when=core.Before,
        operation=core.Insert | core.Delete,
        func="SELECT RAISE(ABORT, 'blocked');",
    )
    stmts = trigger.compile(TestModel)
    assert len(stmts) == 2
    assert "BEFORE INSERT" in stmts[0]
    assert "BEFORE DELETE" in stmts[1]


def test_compile_update_of(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="update_of",
        when=core.Before,
        operation=core.UpdateOf("int_field", "char_field"),
        func="SELECT RAISE(ABORT, 'blocked');",
    )
    stmts = trigger.compile(TestModel)
    assert "UPDATE OF int_field, char_field" in stmts[0]


def test_install_uninstall(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="installable",
        when=core.Before,
        operation=core.Insert,
        func="SELECT RAISE(ABORT, 'blocked');",
    )
    trigger.install(TestModel)

    # Verify trigger exists in sqlite_master
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name='sqlitetrigger_tests_testmodel_installable'"
        )
        assert cursor.fetchone() is not None

    trigger.uninstall(TestModel)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name='sqlitetrigger_tests_testmodel_installable'"
        )
        assert cursor.fetchone() is None


def test_func_rendering(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="func_test",
        when=core.Before,
        operation=core.Delete,
        func=core.Func("SELECT RAISE(ABORT, 'no deletes on {meta.db_table}');"),
    )
    stmts = trigger.compile(TestModel)
    assert "no deletes on tests_testmodel" in stmts[0]


def test_func_columns(db):
    from tests.models import TestModel

    trigger = core.Trigger(
        name="func_cols",
        when=core.After,
        operation=core.Update,
        func=core.Func("SELECT {columns.int_field} FROM {meta.db_table};"),
    )
    rendered = trigger.render_func(TestModel)
    assert rendered == "SELECT int_field FROM tests_testmodel;"


def test_operations_or():
    combined = core.Insert | core.Update | core.Delete
    assert isinstance(combined, core.Operations)
    assert len(combined.operations) == 3


def test_update_of_requires_columns():
    with pytest.raises(ValueError, match="at least one column"):
        core.UpdateOf()


def test_primitives():
    assert str(core.Before) == "BEFORE"
    assert str(core.After) == "AFTER"
    assert str(core.Insert) == "INSERT"
    assert str(core.Update) == "UPDATE"
    assert str(core.Delete) == "DELETE"
    assert core.Before == core.Timing("BEFORE")
    assert hash(core.Before) == hash(core.Timing("BEFORE"))
