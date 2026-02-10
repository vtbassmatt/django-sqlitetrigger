import pytest
from django.db import IntegrityError, connection, transaction

import sqlitetrigger
from sqlitetrigger import installation


@pytest.fixture(autouse=True)
def _install_triggers(db):
    """Install all registered triggers before each test, uninstall after."""
    installation.install()
    yield
    installation.uninstall()


def _trigger_error(match):
    """Context manager that expects an IntegrityError inside an atomic block."""
    return pytest.raises(IntegrityError, match=match)


@pytest.mark.django_db(transaction=True)
class TestProtect:
    def test_protect_delete(self):
        from tests.models import ProtectedModel

        obj = ProtectedModel.objects.create(name="test")
        with _trigger_error("Cannot delete"):
            obj.delete()

    def test_protect_allows_create(self):
        from tests.models import ProtectedModel

        obj = ProtectedModel.objects.create(name="test")
        assert obj.pk is not None

    def test_protect_allows_update(self):
        from tests.models import ProtectedModel

        obj = ProtectedModel.objects.create(name="test")
        obj.name = "updated"
        obj.save()
        obj.refresh_from_db()
        assert obj.name == "updated"


@pytest.mark.django_db(transaction=True)
class TestMultiOpProtect:
    def test_protect_delete(self):
        from tests.models import MultiOpProtectedModel

        obj = MultiOpProtectedModel.objects.create(name="test")
        with _trigger_error("Cannot"):
            obj.delete()

    def test_protect_update(self):
        from tests.models import MultiOpProtectedModel

        obj = MultiOpProtectedModel.objects.create(name="test")
        obj.name = "changed"
        with _trigger_error("Cannot"):
            obj.save()


@pytest.mark.django_db(transaction=True)
class TestReadOnly:
    def test_readonly_field_blocked(self):
        from tests.models import ReadOnlyModel

        obj = ReadOnlyModel.objects.create(name="test", created_at="yesterday")
        obj.created_at = "today"
        with _trigger_error("read-only"):
            obj.save()

    def test_readonly_other_fields_ok(self):
        from tests.models import ReadOnlyModel

        obj = ReadOnlyModel.objects.create(name="test", created_at="yesterday")
        obj.name = "updated"
        obj.save()
        obj.refresh_from_db()
        assert obj.name == "updated"


@pytest.mark.django_db(transaction=True)
class TestSoftDelete:
    def test_soft_delete(self):
        from tests.models import SoftDeleteModel

        obj = SoftDeleteModel.objects.create(name="test", is_active=True)
        pk = obj.pk
        obj.delete()

        # Object should still exist but be inactive
        obj = SoftDeleteModel.objects.get(pk=pk)
        assert obj.is_active is False

    def test_soft_delete_count(self):
        from tests.models import SoftDeleteModel

        SoftDeleteModel.objects.create(name="a", is_active=True)
        SoftDeleteModel.objects.create(name="b", is_active=True)
        assert SoftDeleteModel.objects.count() == 2

        SoftDeleteModel.objects.filter(name="a").delete()
        # Still 2 rows, but one is inactive
        assert SoftDeleteModel.objects.count() == 2
        assert SoftDeleteModel.objects.filter(is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
class TestFSM:
    def test_valid_transition(self):
        from tests.models import FSMModel

        obj = FSMModel.objects.create(status="draft")
        obj.status = "pending"
        obj.save()
        obj.refresh_from_db()
        assert obj.status == "pending"

    def test_valid_transition_chain(self):
        from tests.models import FSMModel

        obj = FSMModel.objects.create(status="draft")
        obj.status = "pending"
        obj.save()
        obj.status = "completed"
        obj.save()
        obj.refresh_from_db()
        assert obj.status == "completed"

    def test_invalid_transition(self):
        from tests.models import FSMModel

        obj = FSMModel.objects.create(status="draft")
        obj.status = "completed"
        with _trigger_error("Invalid transition"):
            obj.save()

    def test_no_change_ok(self):
        from tests.models import FSMModel

        obj = FSMModel.objects.create(status="draft")
        obj.status = "draft"
        obj.save()  # No change, trigger shouldn't fire


@pytest.mark.django_db(transaction=True)
class TestInstallation:
    def test_status(self):
        results = installation.status()
        assert len(results) > 0
        for item in results:
            assert item["status"] == "INSTALLED"

    def test_status_outdated(self):
        """Modifying a trigger's SQL in sqlite_master marks it OUTDATED."""
        results = installation.status()
        # Find a trigger name that's installed
        trigger_name = results[0]["trigger_name"]
        # Drop it and recreate with different SQL
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
            # Figure out the table from the trigger name
            cursor.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='trigger' AND name=?",
                [trigger_name],
            )
            row = cursor.fetchone()
            if row is None:
                # It was dropped, recreate with different body
                # Parse table from trigger name: sqlitetrigger_{table}_{name}
                parts = trigger_name.split("_", 2)  # ['sqlitetrigger', table, ...]
                table = results[0].get("trigger_name", "").replace("sqlitetrigger_", "").rsplit("_", 1)[0]
                # Just create it on the first model's table
                from sqlitetrigger import registry
                first_model, first_trigger = registry.registered()[0]
                table = first_model._meta.db_table
                cursor.execute(
                    f"CREATE TRIGGER {trigger_name} "
                    f"BEFORE INSERT ON {table} "
                    f"BEGIN SELECT 'outdated'; END;"
                )
        results = installation.status()
        statuses = {r["trigger_name"]: r["status"] for r in results}
        assert statuses[trigger_name] == "OUTDATED"

    def test_uninstall_and_reinstall(self):
        installation.uninstall()
        results = installation.status()
        for item in results:
            assert item["status"] == "UNINSTALLED"

        installation.install()
        results = installation.status()
        for item in results:
            assert item["status"] == "INSTALLED"

    def test_prune(self):
        # Create an orphaned trigger
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TRIGGER sqlitetrigger_orphan_test "
                "BEFORE INSERT ON tests_testmodel "
                "BEGIN SELECT 1; END;"
            )

        pruned = installation.prune()
        assert "sqlitetrigger_orphan_test" in pruned

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND name='sqlitetrigger_orphan_test'"
            )
            assert cursor.fetchone() is None


class TestContribValidation:
    def test_readonly_requires_fields(self):
        with pytest.raises(ValueError, match="at least one field"):
            sqlitetrigger.ReadOnly(name="bad", fields=[])

    def test_softdelete_requires_field(self):
        with pytest.raises(ValueError, match="requires a 'field'"):
            sqlitetrigger.SoftDelete(name="bad", value=False)

    def test_softdelete_requires_value(self):
        with pytest.raises(ValueError, match="requires a 'value'"):
            sqlitetrigger.SoftDelete(name="bad", field="is_active")

    def test_fsm_requires_field(self):
        with pytest.raises(ValueError, match="requires a 'field'"):
            sqlitetrigger.FSM(name="bad", transitions=[("a", "b")])

    def test_fsm_requires_transitions(self):
        with pytest.raises(ValueError, match="at least one transition"):
            sqlitetrigger.FSM(name="bad", field="status", transitions=[])


@pytest.mark.django_db(transaction=True)
class TestSoftDeleteFormatValue:
    def test_soft_delete_with_int_value(self):
        """SoftDelete with an integer value."""
        from django.db import models

        trigger = sqlitetrigger.SoftDelete(name="sd_int", field="int_field", value=0)
        assert trigger._format_value() == "0"

    def test_soft_delete_with_float_value(self):
        trigger = sqlitetrigger.SoftDelete(name="sd_float", field="int_field", value=3.14)
        assert trigger._format_value() == "3.14"

    def test_soft_delete_with_string_value(self):
        trigger = sqlitetrigger.SoftDelete(name="sd_str", field="char_field", value="deleted")
        assert trigger._format_value() == "'deleted'"

    def test_soft_delete_with_true_value(self):
        trigger = sqlitetrigger.SoftDelete(name="sd_true", field="is_active", value=True)
        assert trigger._format_value() == "1"
