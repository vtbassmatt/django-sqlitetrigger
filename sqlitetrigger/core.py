"""Core trigger classes and primitives for SQLite triggers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import DEFAULT_DB_ALIAS

if TYPE_CHECKING:
    from django.db.models import Model

    from sqlitetrigger.conditions import Condition

# Max trigger name length (SQLite has no formal limit, but keep it reasonable)
MAX_NAME_LENGTH = 63


class _AttrDict(dict):
    """A dictionary where keys can be accessed as attributes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


class _Primitive:
    def __init__(self, name: str):
        assert name in self.values
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.name == other.name

    def __or__(self, other):
        if isinstance(other, Operations):
            return Operations(self, *other.operations)
        return Operations(self, other)


class Timing(_Primitive):
    values = ("BEFORE", "AFTER")


Before = Timing("BEFORE")
"""Row-level BEFORE trigger"""

After = Timing("AFTER")
"""Row-level AFTER trigger"""


class Operation(_Primitive):
    values = ("INSERT", "UPDATE", "DELETE")


Insert = Operation("INSERT")
"""INSERT operation"""

Update = Operation("UPDATE")
"""UPDATE operation"""

Delete = Operation("DELETE")
"""DELETE operation"""


class UpdateOf:
    """UPDATE OF specific columns."""

    def __init__(self, *columns: str):
        if not columns:
            raise ValueError("UpdateOf requires at least one column")
        self.columns = columns

    def __str__(self):
        return f"UPDATE OF {', '.join(self.columns)}"

    def __repr__(self):
        return f"UpdateOf({', '.join(repr(c) for c in self.columns)})"

    def __hash__(self):
        return hash(("UPDATE OF", self.columns))

    def __eq__(self, other):
        return isinstance(other, UpdateOf) and self.columns == other.columns

    def __or__(self, other):
        if isinstance(other, Operations):
            return Operations(self, *other.operations)
        return Operations(self, other)


class Operations:
    """Multiple operations combined with |."""

    def __init__(self, *operations):
        self.operations = operations

    def __str__(self):
        return " OR ".join(str(op) for op in self.operations)

    def __or__(self, other):
        if isinstance(other, Operations):
            return Operations(*self.operations, *other.operations)
        return Operations(*self.operations, other)


class Trigger:
    """Base class for SQLite triggers.

    Triggers are defined declaratively and compiled to CREATE TRIGGER SQL.

    Attributes:
        name: Trigger name (must be unique per table).
        when: Timing — Before or After.
        operation: Operation — Insert, Update, Delete, UpdateOf, or combined with |.
        condition: Optional WHEN clause (a Condition, Q, or raw SQL string).
        func: The trigger body SQL. Subclasses typically override get_func().
    """

    name: str = ""
    when: Timing | None = None
    operation: Operation | UpdateOf | Operations | None = None
    condition: Condition | str | None = None
    func: Func | str | None = None

    def __init__(
        self,
        *,
        name: str = "",
        when: Timing | None = None,
        operation: Operation | UpdateOf | Operations | None = None,
        condition: Condition | str | None = None,
        func: Func | str | None = None,
    ):
        self.name = name or self.__class__.name
        self.when = when or self.__class__.when
        self.operation = operation if operation is not None else self.__class__.operation
        self.condition = condition if condition is not None else self.__class__.condition
        self.func = func if func is not None else self.__class__.func

        if not self.name:
            raise ValueError("Trigger must have a name")
        if len(self.name) > MAX_NAME_LENGTH:
            raise ValueError(f"Trigger name must be {MAX_NAME_LENGTH} characters or less")
        if self.when is None:
            raise ValueError("Trigger must have a 'when' (Before or After)")
        if self.operation is None:
            raise ValueError("Trigger must have an 'operation'")

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name!r})"

    def get_pgid(self, model: type[Model]) -> str:
        """Get the full trigger identifier for the database."""
        table = model._meta.db_table
        return f"sqlitetrigger_{table}_{self.name}"

    def get_func(self, model: type[Model]) -> Func | str:
        """Return the trigger body (a Func or raw SQL string).

        Subclasses override this to generate appropriate SQL.
        """
        if self.func:
            return self.func
        raise NotImplementedError("Trigger subclasses must implement get_func() or set func")

    def get_func_template_kwargs(self, model: type[Model]) -> dict[str, Any]:
        """Return keyword arguments for rendering a Func template.

        Provides `meta`, `fields`, and `columns` variables so that Func
        templates like `"{columns.id}"` or `"{meta.db_table}"` resolve
        against the model.
        """
        fields = _AttrDict({field.name: field for field in model._meta.fields})
        columns = _AttrDict({field.name: field.column for field in model._meta.fields})
        return {"meta": model._meta, "fields": fields, "columns": columns}

    def render_func(self, model: type[Model]) -> str:
        """Render the trigger body SQL, resolving Func templates if needed."""
        func = self.get_func(model)
        if isinstance(func, Func):
            return func.render(**self.get_func_template_kwargs(model))
        return func

    def get_condition_sql(self, model: type[Model]) -> str:
        """Render the WHEN clause SQL, or empty string if no condition."""
        if self.condition is None:
            return ""
        if isinstance(self.condition, str):
            return f"\n    WHEN ({self.condition})"
        return f"\n    WHEN ({self.condition.resolve(model)})"

    def _get_operation_sql(self) -> str:
        """Render the operation clause."""
        if isinstance(self.operation, Operations):
            # SQLite doesn't support multiple operations in one trigger.
            # We'll need multiple triggers — but for now, just use the first.
            # The install() method handles splitting.
            return str(self.operation.operations[0])
        return str(self.operation)

    def _iter_operations(self):
        """Iterate individual operations (handles Operations combinator)."""
        if isinstance(self.operation, Operations):
            yield from self.operation.operations
        else:
            yield self.operation

    def compile(self, model: type[Model]) -> list[str]:
        """Compile to CREATE TRIGGER SQL statement(s).

        Returns a list because SQLite requires separate triggers for
        each operation when multiple are specified.
        """
        table = model._meta.db_table
        func_sql = self.render_func(model)
        condition_sql = self.get_condition_sql(model)
        statements = []

        for op in self._iter_operations():
            # Include operation name in trigger ID when there are multiple operations
            if isinstance(self.operation, Operations):
                op_suffix = str(op).lower().replace(" ", "_")
                trigger_id = f"sqlitetrigger_{table}_{self.name}_{op_suffix}"
            else:
                trigger_id = self.get_pgid(model)

            sql = (
                f"CREATE TRIGGER {trigger_id}\n"
                f"    {self.when} {op} ON {table}\n"
                f"    FOR EACH ROW{condition_sql}\n"
                f"BEGIN\n"
                f"    {func_sql}\n"
                f"END;"
            )
            statements.append(sql)

        return statements

    def compile_drop(self, model: type[Model]) -> list[str]:
        """Compile DROP TRIGGER SQL statement(s)."""
        table = model._meta.db_table
        statements = []
        for op in self._iter_operations():
            if isinstance(self.operation, Operations):
                op_suffix = str(op).lower().replace(" ", "_")
                trigger_id = f"sqlitetrigger_{table}_{self.name}_{op_suffix}"
            else:
                trigger_id = self.get_pgid(model)
            statements.append(f"DROP TRIGGER IF EXISTS {trigger_id};")
        return statements

    def install(self, model: type[Model], *, database: str = DEFAULT_DB_ALIAS) -> None:
        """Install this trigger into the database."""
        from django.db import connections

        connection = connections[database]
        drop_stmts = self.compile_drop(model)
        create_stmts = self.compile(model)

        with connection.cursor() as cursor:
            for stmt in drop_stmts:
                cursor.execute(stmt)
            for stmt in create_stmts:
                cursor.execute(stmt)

    def uninstall(self, model: type[Model], *, database: str = DEFAULT_DB_ALIAS) -> None:
        """Remove this trigger from the database."""
        from django.db import connections

        connection = connections[database]
        drop_stmts = self.compile_drop(model)

        with connection.cursor() as cursor:
            for stmt in drop_stmts:
                cursor.execute(stmt)

    def register(self, model: type[Model]) -> None:
        """Register this trigger with the global registry."""
        from sqlitetrigger import registry

        uri = f"{model._meta.label}:{self.name}"
        registry.set(uri, model=model, trigger=self)


class Func:
    """
    Allows for rendering a function with access to the "meta", "fields",
    and "columns" variables of the current model.

    For example, `func=Func("SELECT {columns.id} FROM {meta.db_table};")` makes it
    possible to do inline SQL in the `Meta` of a model and reference its properties.
    """

    def __init__(self, func):
        self.func = func

    def render(self, **kwargs) -> str:
        """
        Render the SQL of the function.

        Args:
            **kwargs: Keyword arguments to pass to the function template.

        Returns:
            The rendered SQL.
        """
        return self.func.format(**kwargs)
