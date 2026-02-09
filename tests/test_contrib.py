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
