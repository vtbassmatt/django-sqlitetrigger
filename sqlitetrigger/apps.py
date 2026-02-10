import django.apps
from django.db.models import options

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


class SqliteTriggerConfig(django.apps.AppConfig):
    name = "sqlitetrigger"

    def ready(self):
        from sqlitetrigger import core

        _patch_migrations()

        # Auto-register triggers from model Meta
        for model in django.apps.apps.get_models():
            for trigger in getattr(model._meta, "triggers", []):
                if not isinstance(trigger, core.Trigger):
                    raise TypeError(
                        f"Triggers in {model} Meta must be sqlitetrigger.Trigger instances"
                    )
                trigger.register(model)
