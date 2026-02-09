"""Global trigger registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from django.db.models import Model

    from sqlitetrigger.core import Trigger


class _Registry(dict):
    def __setitem__(self, key: str, value: tuple[type[Model], Trigger]):
        model, trigger = value
        expected_key = f"{model._meta.label}:{trigger.name}"
        assert expected_key == key, f"Key mismatch: {key} != {expected_key}"

        # Check for duplicate trigger names on the same table
        for existing_key, (existing_model, existing_trigger) in self.items():
            if existing_key == key:
                continue
            if (
                existing_model._meta.db_table == model._meta.db_table
                and existing_trigger.name == trigger.name
            ):
                raise KeyError(
                    f'Trigger name "{trigger.name}" already used for '
                    f'table "{model._meta.db_table}".'
                )

        super().__setitem__(key, (model, trigger))

    def __getitem__(self, key: str):
        if ":" not in key:
            raise ValueError(
                'Trigger URI must be in the format "app_label.model_name:trigger_name"'
            )
        if key not in self:
            raise KeyError(f'URI "{key}" not found in sqlitetrigger registry')
        return super().__getitem__(key)


_registry = _Registry()


def set(uri: str, *, model: type[Model], trigger: Trigger) -> None:
    """Register a trigger."""
    _registry[uri] = (model, trigger)


def delete(uri: str) -> None:
    """Remove a trigger from the registry."""
    del _registry[uri]


def registered(*uris: str) -> list[tuple[type[Model], Trigger]]:
    """Get registered trigger objects.

    Args:
        *uris: URIs to look up. If none, returns all registered triggers.
              Format: "app_label.model_name:trigger_name"
    """
    if uris:
        return [_registry[uri] for uri in uris]
    return list(_registry.values())


def register(*triggers: Trigger) -> Callable:
    """Register triggers with a model class (decorator).

    Example:
        @sqlitetrigger.register(
            sqlitetrigger.Protect(name="no_delete", operation=sqlitetrigger.Delete)
        )
        class MyModel(models.Model):
            pass
    """

    def _wrapper(model_class):
        for trigger in triggers:
            trigger.register(model_class)
        return model_class

    return _wrapper
