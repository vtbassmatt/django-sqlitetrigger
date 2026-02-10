import pytest

from sqlitetrigger.conditions import Condition, F, Q


class MockMeta:
    class _field:
        column = "col_name"

    def get_field(self, name):
        # Return a mock field with column = name
        class FakeField:
            column = name
        return FakeField()


class MockModel:
    _meta = MockMeta()


def test_f_old():
    f = F("old__name")
    assert f.resolve() == "OLD.name"


def test_f_new():
    f = F("new__status")
    assert f.resolve() == "NEW.status"


def test_f_invalid():
    with pytest.raises(ValueError, match="must be 'old__field' or 'new__field'"):
        F("bad").resolve()


def test_f_no_prefix():
    with pytest.raises(ValueError, match="must be 'old__field' or 'new__field'"):
        F("name").resolve()


def test_q_exact():
    q = Q(old__status="active")
    sql = q.resolve(MockModel)
    assert sql == "OLD.status = 'active'"


def test_q_ne():
    q = Q(old__status__ne="deleted")
    sql = q.resolve(MockModel)
    assert sql == "OLD.status != 'deleted'"


def test_q_gt():
    q = Q(new__count__gt=10)
    sql = q.resolve(MockModel)
    assert sql == "NEW.count > 10"


def test_q_isnull():
    q = Q(old__name__isnull=True)
    sql = q.resolve(MockModel)
    assert sql == "OLD.name IS NULL"


def test_q_isnull_false():
    q = Q(old__name__isnull=False)
    sql = q.resolve(MockModel)
    assert sql == "OLD.name IS NOT NULL"


def test_q_is():
    q = Q(old__name__is=F("new__name"))
    sql = q.resolve(MockModel)
    assert sql == "OLD.name IS NEW.name"


def test_q_isnot():
    q = Q(old__name__isnot=F("new__name"))
    sql = q.resolve(MockModel)
    assert sql == "OLD.name IS NOT NEW.name"


def test_q_multiple_lookups():
    q = Q(old__status="active", new__count__gt=0)
    sql = q.resolve(MockModel)
    assert "OLD.status = 'active'" in sql
    assert "NEW.count > 0" in sql
    assert " AND " in sql


def test_q_bool_value():
    q = Q(new__is_active=True)
    sql = q.resolve(MockModel)
    assert sql == "NEW.is_active = 1"


def test_q_none_value():
    q = Q(new__name=None)
    sql = q.resolve(MockModel)
    assert sql == "NEW.name = NULL"


def test_q_string_escaping():
    q = Q(old__name="it's")
    sql = q.resolve(MockModel)
    assert sql == "OLD.name = 'it''s'"


def test_q_invalid_prefix():
    with pytest.raises(ValueError, match="must start with 'old__' or 'new__'"):
        Q(bad__field="value").resolve(MockModel)


def test_q_empty():
    with pytest.raises(ValueError, match="requires at least one"):
        Q()


def test_condition_and():
    q1 = Q(old__a=1)
    q2 = Q(new__b=2)
    combined = q1 & q2
    sql = combined.resolve(MockModel)
    assert sql == "(OLD.a = 1) AND (NEW.b = 2)"


def test_condition_or():
    q1 = Q(old__a=1)
    q2 = Q(new__b=2)
    combined = q1 | q2
    sql = combined.resolve(MockModel)
    assert sql == "(OLD.a = 1) OR (NEW.b = 2)"


def test_condition_invert():
    q = Q(old__a=1)
    negated = ~q
    sql = negated.resolve(MockModel)
    assert sql == "NOT (OLD.a = 1)"


def test_f_repr():
    f = F("old__name")
    assert repr(f) == "F('old__name')"


def test_q_repr():
    q = Q(old__status="active")
    assert repr(q) == "Q(old__status='active')"


def test_q_resolve_field_no_model():
    q = Q(old__my_field=1)
    # When model is None (not passed), field name is used as-is
    sql = q.resolve(None)
    assert sql == "OLD.my_field = 1"
