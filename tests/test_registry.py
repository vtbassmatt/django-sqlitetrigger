import pytest

import sqlitetrigger
from sqlitetrigger import registry
from sqlitetrigger.core import Trigger, Before, Insert


@pytest.fixture(autouse=True)
def _clean_registry():
    """Save and restore the registry around each test."""
    saved = dict(registry._registry)
    yield
    registry._registry.clear()
    registry._registry.update(saved)


def test_register_decorator(db):
    from tests.models import TestModel

    trigger = Trigger(name="test_reg", when=Before, operation=Insert, func="SELECT 1;")
    trigger.register(TestModel)

    results = registry.registered()
    uris = [f"{m._meta.label}:{t.name}" for m, t in results]
    assert "tests.TestModel:test_reg" in uris


def test_registered_by_uri(db):
    from tests.models import TestModel

    trigger = Trigger(name="test_by_uri", when=Before, operation=Insert, func="SELECT 1;")
    trigger.register(TestModel)

    results = registry.registered("tests.TestModel:test_by_uri")
    assert len(results) == 1
    assert results[0][1].name == "test_by_uri"


def test_invalid_uri_format():
    with pytest.raises(ValueError, match="format"):
        registry._registry["bad_key"]


def test_missing_uri():
    with pytest.raises(KeyError, match="not found"):
        registry._registry["app.Model:nonexistent"]


def test_duplicate_trigger_name(db):
    from tests.models import TestModel

    t1 = Trigger(name="dup_name", when=Before, operation=Insert, func="SELECT 1;")
    t1.register(TestModel)

    # Registering same name on same model with same key should overwrite
    t2 = Trigger(name="dup_name", when=Before, operation=Insert, func="SELECT 2;")
    t2.register(TestModel)  # same URI, should work


def test_register_function_decorator(db):
    from django.db import models

    trigger = sqlitetrigger.Protect(name="func_reg", operation=sqlitetrigger.Delete)

    @sqlitetrigger.register(trigger)
    class TempModel(models.Model):
        class Meta:
            app_label = "tests"

    results = registry.registered()
    uris = [f"{m._meta.label}:{t.name}" for m, t in results]
    assert "tests.TempModel:func_reg" in uris


def test_delete_from_registry(db):
    from tests.models import TestModel

    trigger = Trigger(name="del_test", when=Before, operation=Insert, func="SELECT 1;")
    trigger.register(TestModel)

    uri = "tests.TestModel:del_test"
    assert any(u == uri for u in [f"{m._meta.label}:{t.name}" for m, t in registry.registered()])

    registry.delete(uri)
    assert not any(
        u == uri for u in [f"{m._meta.label}:{t.name}" for m, t in registry.registered()]
    )


def test_duplicate_trigger_name_different_model(db):
    """Registering the same trigger name on two models sharing the same table should fail."""
    from django.db import models

    t1 = Trigger(name="shared_name", when=Before, operation=Insert, func="SELECT 1;")

    class ModelA(models.Model):
        class Meta:
            app_label = "tests"
            db_table = "tests_shared_table"

    class ModelB(models.Model):
        class Meta:
            app_label = "tests"
            db_table = "tests_shared_table"

    t1.register(ModelA)

    t2 = Trigger(name="shared_name", when=Before, operation=Insert, func="SELECT 2;")
    with pytest.raises(KeyError, match="already used"):
        t2.register(ModelB)
