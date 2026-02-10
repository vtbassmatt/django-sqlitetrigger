"""Condition system for SQLite trigger WHEN clauses."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import Model


class F:
    """Reference to a field on OLD or NEW row.

    Usage:
        F("old__name")  # OLD.name
        F("new__status")  # NEW.status
    """

    def __init__(self, ref: str):
        self.ref = ref

    def resolve(self, model: type[Model] | None = None) -> str:
        parts = self.ref.split("__", 1)
        if len(parts) != 2 or parts[0] not in ("old", "new"):
            raise ValueError(
                f"F() reference must be 'old__field' or 'new__field', got '{self.ref}'"
            )
        prefix = parts[0].upper()
        field_name = parts[1]

        if model is not None:
            # Resolve to the actual database column name
            field_name = model._meta.get_field(field_name).column

        return f"{prefix}.{field_name}"

    def __repr__(self):
        return f"F({self.ref!r})"


class Condition:
    """Base class for trigger conditions (WHEN clauses)."""

    def resolve(self, model: type[Model]) -> str:
        raise NotImplementedError  # pragma: no cover

    def __and__(self, other):
        return _Combined(self, other, "AND")

    def __or__(self, other):
        return _Combined(self, other, "OR")

    def __invert__(self):
        return _Negated(self)


class _Combined(Condition):
    def __init__(self, left: Condition, right: Condition, connector: str):
        self.left = left
        self.right = right
        self.connector = connector

    def resolve(self, model: type[Model]) -> str:
        left_sql = self.left.resolve(model)
        right_sql = self.right.resolve(model)
        return f"({left_sql}) {self.connector} ({right_sql})"


class _Negated(Condition):
    def __init__(self, condition: Condition):
        self.condition = condition

    def resolve(self, model: type[Model]) -> str:
        return f"NOT ({self.condition.resolve(model)})"


class Q(Condition):
    """Build WHEN clause conditions using Django-like field lookups.

    Supports lookups on OLD and NEW row references:
        Q(old__status="active")         -> OLD.status = 'active'
        Q(new__name__isnull=True)       -> NEW.name IS NULL
        Q(old__field__ne=F("new__field")) -> OLD.field != NEW.field

    Supported lookups:
        (none)      exact equality (=)
        __ne        not equal (!=)
        __gt        greater than (>)
        __gte       greater than or equal (>=)
        __lt        less than (<)
        __lte       less than or equal (<=)
        __isnull    IS NULL / IS NOT NULL
        __is        IS (null-safe equality)
        __isnot     IS NOT (null-safe inequality)
    """

    LOOKUP_MAP = {
        "eq": "=",
        "ne": "!=",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
    }

    def __init__(self, **kwargs):
        if not kwargs:
            raise ValueError("Q() requires at least one keyword argument")
        self.lookups = kwargs

    def _parse_key(self, key: str) -> tuple[str, str, str]:
        """Parse 'old__field__lookup' into (prefix, field, lookup)."""
        parts = key.split("__")
        if len(parts) < 2 or parts[0] not in ("old", "new"):
            raise ValueError(
                f"Q() keys must start with 'old__' or 'new__', got '{key}'"
            )
        prefix = parts[0].upper()

        # Check if last part is a lookup
        if len(parts) >= 3 and parts[-1] in (*self.LOOKUP_MAP, "isnull", "is", "isnot"):
            lookup = parts[-1]
            field = "__".join(parts[1:-1])
        else:
            lookup = "eq"
            field = "__".join(parts[1:])

        return prefix, field, lookup

    def _resolve_value(self, value, model: type[Model] | None = None) -> str:
        """Render a value for use in SQL."""
        if isinstance(value, F):
            return value.resolve(model)
        if isinstance(value, bool):
            return "1" if value else "0"
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        # String value — quote it
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def _resolve_field(self, prefix: str, field: str, model: type[Model] | None = None) -> str:
        """Resolve field name to column name."""
        if model is not None:
            column = model._meta.get_field(field).column
        else:
            column = field
        return f"{prefix}.{column}"

    def resolve(self, model: type[Model]) -> str:
        clauses = []
        for key, value in self.lookups.items():
            prefix, field, lookup = self._parse_key(key)
            col_ref = self._resolve_field(prefix, field, model)

            if lookup == "isnull":
                if value:
                    clauses.append(f"{col_ref} IS NULL")
                else:
                    clauses.append(f"{col_ref} IS NOT NULL")
            elif lookup == "is":
                val_sql = self._resolve_value(value, model)
                clauses.append(f"{col_ref} IS {val_sql}")
            elif lookup == "isnot":
                val_sql = self._resolve_value(value, model)
                clauses.append(f"{col_ref} IS NOT {val_sql}")
            else:
                op = self.LOOKUP_MAP[lookup]
                val_sql = self._resolve_value(value, model)
                clauses.append(f"{col_ref} {op} {val_sql}")

        return " AND ".join(clauses)

    def __repr__(self):
        args = ", ".join(f"{k}={v!r}" for k, v in self.lookups.items())
        return f"Q({args})"
