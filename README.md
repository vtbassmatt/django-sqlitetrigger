# django-sqlitetrigger

SQLite trigger support integrated with Django models.

Inspired by [django-pgtrigger](https://github.com/AmbitionEng/django-pgtrigger), this package provides declarative trigger support for SQLite-backed Django projects.

## Quick start

Install and add `sqlitetrigger` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "sqlitetrigger",
    # ...
]
```

Add triggers to your models:

```python
import sqlitetrigger

class ProtectedModel(models.Model):
    """This model cannot be deleted!"""

    class Meta:
        triggers = [
            sqlitetrigger.Protect(name="protect_deletes", operation=sqlitetrigger.Delete)
        ]
```

Install triggers:

```bash
python manage.py sqlitetrigger install
```

## Built-in triggers

- **Protect** — prevent insert, update, or delete operations
- **ReadOnly** — prevent changes to specific fields
- **SoftDelete** — intercept deletes and set a field instead
- **FSM** — enforce valid field state transitions

## Running tests

```bash
uv run pytest
```
