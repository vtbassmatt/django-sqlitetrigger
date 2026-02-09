import django.apps
from django.db.models import options

# Patch Meta to accept triggers BEFORE models are loaded
if "triggers" not in options.DEFAULT_NAMES:
    options.DEFAULT_NAMES = tuple(options.DEFAULT_NAMES) + ("triggers",)


class SqliteTriggerConfig(django.apps.AppConfig):
    name = "sqlitetrigger"

    def ready(self):
        from sqlitetrigger import core, registry as _registry

        # Auto-register triggers from model Meta
        for model in django.apps.apps.get_models():
            for trigger in getattr(model._meta, "triggers", []):
                if not isinstance(trigger, core.Trigger):
                    raise TypeError(
                        f"Triggers in {model} Meta must be sqlitetrigger.Trigger instances"
                    )
                trigger.register(model)
