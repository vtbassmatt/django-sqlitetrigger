"""Migration operations and autodetector mixin for sqlitetrigger."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from django.db import transaction
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.autodetector import OperationDependency
from django.db.migrations.operations.base import OperationCategory
from django.db.migrations.operations.fields import AddField
from django.db.migrations.operations.models import CreateModel, IndexOperation
from django.db.migrations.state import ModelState, ProjectState
from django.db.models import Model


class CompiledTrigger:
    """A compiled trigger stored in migration state.

    Contains the trigger name and SQL needed to install/uninstall it.
    This is what gets serialized into migration files via deconstruct().
    """

    def __init__(self, *, name: str, install_sql: list[str], drop_sql: list[str]):
        self.name = name
        self.install_sql = install_sql
        self.drop_sql = drop_sql
        self.hash = hashlib.sha1(
            "\n".join(install_sql).encode()
        ).hexdigest()

    def __eq__(self, other):
        if not isinstance(other, CompiledTrigger):
            return NotImplemented
        return self.name == other.name and self.hash == other.hash

    def __repr__(self):
        return f"CompiledTrigger(name={self.name!r})"

    def deconstruct(self) -> tuple[str, Sequence[Any], dict[str, Any]]:
        path = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        return path, [], {
            "name": self.name,
            "install_sql": self.install_sql,
            "drop_sql": self.drop_sql,
        }


def _compile_trigger(model: type[Model], trigger) -> CompiledTrigger:
    """Compile a core.Trigger into a CompiledTrigger for migration state."""
    return CompiledTrigger(
        name=trigger.name,
        install_sql=trigger.compile(model),
        drop_sql=trigger.compile_drop(model),
    )


def _add_trigger(
    schema_editor: BaseDatabaseSchemaEditor,
    model: type[Model],
    trigger: CompiledTrigger,
) -> None:
    """Install a compiled trigger."""
    for sql in trigger.drop_sql:
        schema_editor.execute(sql, params=None)
    for sql in trigger.install_sql:
        schema_editor.execute(sql, params=None)


def _remove_trigger(
    schema_editor: BaseDatabaseSchemaEditor,
    model: type[Model],
    trigger: CompiledTrigger,
) -> None:
    """Remove a compiled trigger."""
    for sql in trigger.drop_sql:
        schema_editor.execute(sql, params=None)


class AddTrigger(IndexOperation):
    option_name = "triggers"
    category = OperationCategory.ADDITION

    def __init__(self, model_name: str, trigger: CompiledTrigger) -> None:
        self.model_name = model_name
        self.trigger = trigger

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        model_state = state.models[app_label, self.model_name]
        model_state.options["triggers"] = model_state.options.get("triggers", []) + [self.trigger]
        state.reload_model(app_label, self.model_name, delay=True)

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            _add_trigger(schema_editor, model, self.trigger)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            _remove_trigger(schema_editor, model, self.trigger)

    def describe(self) -> str:
        return f"Create trigger {self.trigger.name} on model {self.model_name}"

    def deconstruct(self) -> tuple[str, Sequence[Any], dict[str, Any]]:
        return (
            self.__class__.__name__,
            [],
            {"model_name": self.model_name, "trigger": self.trigger},
        )

    @property
    def migration_name_fragment(self) -> str:
        return f"{self.model_name_lower}_{self.trigger.name.lower()}"


class RemoveTrigger(IndexOperation):
    option_name = "triggers"
    category = OperationCategory.REMOVAL

    def __init__(self, model_name: str, name: str) -> None:
        self.model_name = model_name
        self.name = name

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        model_state = state.models[app_label, self.model_name]
        triggers = model_state.options.get("triggers", [])
        model_state.options["triggers"] = [t for t in triggers if t.name != self.name]
        state.reload_model(app_label, self.model_name, delay=True)

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            from_model_state = from_state.models[app_label, self.model_name_lower]
            trigger = _get_trigger_by_name(from_model_state, self.name)
            _remove_trigger(schema_editor, model, trigger)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            to_model_state = to_state.models[app_label, self.model_name_lower]
            trigger = _get_trigger_by_name(to_model_state, self.name)
            _add_trigger(schema_editor, model, trigger)

    def describe(self) -> str:
        return f"Remove trigger {self.name} from model {self.model_name}"

    def deconstruct(self) -> tuple[str, Sequence[Any], dict[str, Any]]:
        return (
            self.__class__.__name__,
            [],
            {"model_name": self.model_name, "name": self.name},
        )

    @property
    def migration_name_fragment(self) -> str:
        return f"remove_{self.model_name_lower}_{self.name.lower()}"


def _get_trigger_by_name(model_state: ModelState, name: str) -> CompiledTrigger:
    for trigger in model_state.options.get("triggers", []):
        if trigger.name == name:
            return trigger
    raise ValueError(f"No trigger named {name} on model {model_state.name}")


class MigrationAutodetectorMixin:
    """Mixin for MigrationAutodetector that detects trigger changes."""

    def _detect_changes(self, *args, **kwargs):
        self.altered_triggers = {}
        return super()._detect_changes(*args, **kwargs)

    def _get_add_trigger_op(self, model, trigger):
        if not isinstance(trigger, CompiledTrigger):
            trigger = _compile_trigger(model, trigger)
        return AddTrigger(model_name=model._meta.model_name, trigger=trigger)

    def create_altered_constraints(self):
        """Detect trigger changes on existing models."""
        for app_label, model_name in sorted(self.kept_model_keys | self.kept_proxy_keys):
            old_model_name = self.renamed_models.get((app_label, model_name), model_name)
            old_model_state = self.from_state.models[app_label, old_model_name]
            new_model_state = self.to_state.models[app_label, model_name]
            new_model = self.to_state.apps.get_model(app_label, model_name)

            old_triggers = old_model_state.options.get("triggers", [])
            new_triggers = [
                _compile_trigger(new_model, t)
                for t in new_model_state.options.get("triggers", [])
            ]
            add_triggers = [t for t in new_triggers if t not in old_triggers]
            rem_triggers = [t for t in old_triggers if t not in new_triggers]

            self.altered_triggers[(app_label, model_name)] = {
                "added_triggers": add_triggers,
                "removed_triggers": rem_triggers,
            }

        return super().create_altered_constraints()

    def generate_added_constraints(self):
        for (app_label, model_name), alt in self.altered_triggers.items():
            model = self.to_state.apps.get_model(app_label, model_name)
            for trigger in alt["added_triggers"]:
                self.add_operation(
                    app_label, self._get_add_trigger_op(model=model, trigger=trigger)
                )
        return super().generate_added_constraints()

    def generate_removed_constraints(self):
        for (app_label, model_name), alt in self.altered_triggers.items():
            for trigger in alt["removed_triggers"]:
                self.add_operation(
                    app_label, RemoveTrigger(model_name=model_name, name=trigger.name)
                )
        return super().generate_removed_constraints()

    def generate_created_models(self):
        super().generate_created_models()

        added_models = self.new_model_keys - self.old_model_keys
        added_models = sorted(added_models, key=self.swappable_first_key, reverse=True)

        for app_label, model_name in added_models:
            model = self.to_state.apps.get_model(app_label, model_name)
            model_state = self.to_state.models[app_label, model_name]

            if not model_state.options.get("managed", True):
                continue

            related_fields = {
                op.name: op.field
                for op in self.generated_operations.get(app_label, [])
                if isinstance(op, AddField) and model_name == op.model_name
            }
            related_dependencies = [
                OperationDependency(app_label, model_name, name, OperationDependency.Type.CREATE)
                for name in sorted(related_fields)
            ]
            related_dependencies.append(
                OperationDependency(
                    app_label, model_name, None, OperationDependency.Type.CREATE
                )
            )

            for trigger in model_state.options.pop("triggers", []):
                self.add_operation(
                    app_label,
                    self._get_add_trigger_op(model=model, trigger=trigger),
                    dependencies=related_dependencies,
                )

    def generate_created_proxies(self):
        super().generate_created_proxies()

        added = self.new_proxy_keys - self.old_proxy_keys
        for app_label, model_name in sorted(added):
            model = self.to_state.apps.get_model(app_label, model_name)
            model_state = self.to_state.models[app_label, model_name]

            for trigger in model_state.options.pop("triggers", []):
                self.add_operation(
                    app_label,
                    self._get_add_trigger_op(model=model, trigger=trigger),
                    dependencies=[
                        OperationDependency(
                            app_label, model_name, None, OperationDependency.Type.CREATE
                        )
                    ],
                )

    def generate_deleted_proxies(self):
        deleted = self.old_proxy_keys - self.new_proxy_keys
        for app_label, model_name in sorted(deleted):
            model_state = self.from_state.models[app_label, model_name]
            for trigger in model_state.options.pop("triggers", []):
                self.add_operation(
                    app_label,
                    RemoveTrigger(model_name=model_name, name=trigger.name),
                    dependencies=[
                        OperationDependency(
                            app_label, model_name, None, OperationDependency.Type.CREATE
                        )
                    ],
                )
        super().generate_deleted_proxies()
