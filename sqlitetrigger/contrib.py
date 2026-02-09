"""Built-in trigger classes for common patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlitetrigger import conditions, core

if TYPE_CHECKING:
    from django.db.models import Model


class Protect(core.Trigger):
    """Protect against insert, update, or delete operations.

    Raises an error when the specified operation is attempted.

    Example:
        class MyModel(models.Model):
            class Meta:
                triggers = [
                    Protect(name="no_delete", operation=sqlitetrigger.Delete)
                ]
    """

    when: core.Timing = core.Before

    def get_func(self, model: type[Model]) -> str:
        ops = list(self.operation.operations) if isinstance(
            self.operation, core.Operations
        ) else [self.operation]
        op_names = " or ".join(str(op).lower() for op in ops)
        table = model._meta.db_table
        return f"SELECT RAISE(ABORT, 'Cannot {op_names} rows in {table}');"


class ReadOnly(core.Trigger):
    """Prevent changes to specific fields.

    Example:
        class MyModel(models.Model):
            created_at = models.DateTimeField(auto_now_add=True)

            class Meta:
                triggers = [
                    ReadOnly(
                        name="readonly_created_at",
                        fields=["created_at"],
                    )
                ]
    """

    when: core.Timing = core.Before
    operation: core.Operation = core.Update
    fields: list[str] = []

    def __init__(self, *, fields: list[str] | None = None, **kwargs):
        self.fields = fields or self.__class__.fields
        if not self.fields:
            raise ValueError("ReadOnly trigger requires at least one field")
        super().__init__(**kwargs)

    def get_condition_sql(self, model: type[Model]) -> str:
        """Build WHEN clause checking if any of the fields changed."""
        checks = []
        for field_name in self.fields:
            col = model._meta.get_field(field_name).column
            checks.append(f"OLD.{col} IS NOT NEW.{col}")
        combined = " OR ".join(checks)
        return f"\n    WHEN ({combined})"

    def get_func(self, model: type[Model]) -> str:
        field_names = ", ".join(self.fields)
        table = model._meta.db_table
        return (
            f"SELECT RAISE(ABORT, 'Cannot modify read-only field(s) "
            f"{field_names} on {table}');"
        )


class SoftDelete(core.Trigger):
    """Intercept deletes and set a field instead.

    When a row is deleted, it is instead updated to set the specified
    field to the given value, effectively "soft deleting" the row.

    Example:
        class MyModel(models.Model):
            is_active = models.BooleanField(default=True)

            class Meta:
                triggers = [
                    SoftDelete(name="soft_delete", field="is_active", value=False)
                ]
    """

    when: core.Timing = core.Before
    operation: core.Operation = core.Delete
    field: str = ""
    value: object = None

    def __init__(self, *, field: str = "", value: object = None, **kwargs):
        self.field = field or self.__class__.field
        self.value = value if value is not None else self.__class__.value
        if not self.field:
            raise ValueError("SoftDelete trigger requires a 'field'")
        if self.value is None:
            raise ValueError("SoftDelete trigger requires a 'value'")
        # Force BEFORE DELETE
        kwargs.setdefault("when", core.Before)
        kwargs.setdefault("operation", core.Delete)
        super().__init__(**kwargs)

    def _format_value(self) -> str:
        if isinstance(self.value, bool):
            return "1" if self.value else "0"
        if isinstance(self.value, (int, float)):
            return str(self.value)
        if self.value is None:
            return "NULL"
        escaped = str(self.value).replace("'", "''")
        return f"'{escaped}'"

    def get_func(self, model: type[Model]) -> str:
        table = model._meta.db_table
        col = model._meta.get_field(self.field).column
        pk_col = model._meta.pk.column
        val = self._format_value()
        return (
            f"UPDATE {table} SET {col} = {val} WHERE {pk_col} = OLD.{pk_col};\n"
            f"    SELECT RAISE(IGNORE);"
        )


class FSM(core.Trigger):
    """Enforce valid field state transitions (Finite State Machine).

    Validates that a field can only transition between allowed states.

    Example:
        class Order(models.Model):
            status = models.CharField(max_length=20, default="draft")

            class Meta:
                triggers = [
                    FSM(
                        name="status_fsm",
                        field="status",
                        transitions=[
                            ("draft", "pending"),
                            ("pending", "completed"),
                            ("pending", "cancelled"),
                        ],
                    )
                ]
    """

    when: core.Timing = core.Before
    operation: core.Operation = core.Update
    field: str = ""
    transitions: list[tuple[str, str]] = []

    def __init__(
        self,
        *,
        field: str = "",
        transitions: list[tuple[str, str]] | None = None,
        **kwargs,
    ):
        self.field = field or self.__class__.field
        self.transitions = transitions if transitions is not None else self.__class__.transitions
        if not self.field:
            raise ValueError("FSM trigger requires a 'field'")
        if not self.transitions:
            raise ValueError("FSM trigger requires at least one transition")
        kwargs.setdefault("when", core.Before)
        kwargs.setdefault("operation", core.Update)
        super().__init__(**kwargs)

    def get_condition_sql(self, model: type[Model]) -> str:
        """Only fire when the FSM field actually changes."""
        col = model._meta.get_field(self.field).column
        return f"\n    WHEN (OLD.{col} IS NOT NEW.{col})"

    def get_func(self, model: type[Model]) -> str:
        col = model._meta.get_field(self.field).column
        # Build a CASE that checks if the transition is valid
        valid_checks = []
        for from_state, to_state in self.transitions:
            from_val = f"'{from_state}'"
            to_val = f"'{to_state}'"
            valid_checks.append(
                f"(OLD.{col} = {from_val} AND NEW.{col} = {to_val})"
            )

        valid_expr = " OR ".join(valid_checks)
        return (
            f"SELECT RAISE(ABORT, 'Invalid transition for field {self.field}')\n"
            f"    WHERE NOT ({valid_expr});"
        )
