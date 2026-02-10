import django.apps
from django.conf import settings
from django.db.models import options
from django.db.utils import load_backend

# Patch Meta to accept triggers BEFORE models are loaded
if "triggers" not in options.DEFAULT_NAMES:
    options.DEFAULT_NAMES = tuple(options.DEFAULT_NAMES) + ("triggers",)


def _patch_migrations():
    """Patch the autodetector so makemigrations/migrate detect trigger changes."""
    from django.core.management.commands import makemigrations, migrate
    from django.db.migrations import state

    from sqlitetrigger.migrations import MigrationAutodetectorMixin

    if "triggers" not in state.DEFAULT_NAMES:
        state.DEFAULT_NAMES = tuple(state.DEFAULT_NAMES) + ("triggers",)

    if not issubclass(
        makemigrations.MigrationAutodetector, MigrationAutodetectorMixin
    ):
        makemigrations.MigrationAutodetector = type(
            "MigrationAutodetector",
            (MigrationAutodetectorMixin, makemigrations.MigrationAutodetector),
            {},
        )

    if not issubclass(
        migrate.MigrationAutodetector, MigrationAutodetectorMixin
    ):
        migrate.MigrationAutodetector = type(
            "MigrationAutodetector",
            (MigrationAutodetectorMixin, migrate.MigrationAutodetector),
            {},
        )

    makemigrations.Command.autodetector = makemigrations.MigrationAutodetector
    migrate.Command.autodetector = makemigrations.MigrationAutodetector


def _patch_schema_editor():
    """Patch SQLite's schema editor to preserve triggers across table rebuilds."""
    import django.db.backends.sqlite3.schema as sqlite_schema

    from sqlitetrigger.migrations import DatabaseSchemaEditorMixin

    for config in settings.DATABASES.values():
        backend = load_backend(config["ENGINE"])
        schema_editor_class = backend.DatabaseWrapper.SchemaEditorClass

        if (
            schema_editor_class
            and issubclass(schema_editor_class, sqlite_schema.DatabaseSchemaEditor)
            and not issubclass(schema_editor_class, DatabaseSchemaEditorMixin)
        ):
            backend.DatabaseWrapper.SchemaEditorClass = type(
                "DatabaseSchemaEditor",
                (DatabaseSchemaEditorMixin, schema_editor_class),
                {},
            )


class SqliteTriggerConfig(django.apps.AppConfig):
    name = "sqlitetrigger"

    def ready(self):
        from sqlitetrigger import core

        _patch_migrations()
        _patch_schema_editor()

        # Auto-register triggers from model Meta
        for model in django.apps.apps.get_models():
            for trigger in getattr(model._meta, "triggers", []):
                if not isinstance(trigger, core.Trigger):
                    raise TypeError(
                        f"Triggers in {model} Meta must be sqlitetrigger.Trigger instances"
                    )
                trigger.register(model)
